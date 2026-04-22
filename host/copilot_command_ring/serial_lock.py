# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Cross-platform file lock for serialising access to the USB serial port.

When multiple Copilot CLI sessions run on the same machine (across different
repos), their hook processes may try to open the serial port simultaneously.
This module provides a lightweight file lock so that only one process writes
at a time — preventing port-busy errors and byte-level corruption.

The lock file lives in the OS temp directory so it is visible to all processes
regardless of which repo they run from.

On acquire, the lock file is stamped with ``<pid> <timestamp>``. If a
later process times out waiting for the lock, it checks the stamp: if the
recorded PID is no longer alive and the file's mtime is far older than the
caller's timeout, the lock is treated as orphaned and forcibly stolen. This
keeps a hung or killed CLI process from leaving the ring unreachable.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import time
from types import TracebackType

from .logging_util import get_logger

LOCK_FILENAME = "copilot-command-ring.lock"
# Multiple of the caller's timeout after which a lock held by a dead PID is
# considered orphaned and may be forcibly stolen.
STALE_LOCK_MULTIPLIER = 10.0
# Absolute floor for stale-lock detection so very short timeouts do not
# prematurely steal a lock from a slow-but-healthy peer.
STALE_LOCK_MIN_AGE = 30.0


def _lock_path() -> str:
    """Return the path to the system-wide lock file."""
    return os.path.join(tempfile.gettempdir(), LOCK_FILENAME)


def _pid_is_alive(pid: int) -> bool:
    """Return True if *pid* corresponds to a live process on this host.

    Conservative on error — if we cannot tell, we return True so a healthy
    peer is never stolen from.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415

            process_query_flag = 0x1000
            still_active = 259
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(
                process_query_flag, False, pid,
            )
            if not handle:
                # Access denied → process exists; invalid handle → gone.
                return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED
            try:
                exit_code = ctypes.c_ulong(0)
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == still_active
                return True
            finally:
                kernel32.CloseHandle(handle)
        except (OSError, AttributeError, ImportError):
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours
    except OSError:
        return True
    return True


def _read_lock_stamp(path: str) -> tuple[int, float] | None:
    """Return ``(pid, mtime)`` from the lock file or None on any error."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read().strip()
        mtime = os.path.getmtime(path)
    except (OSError, ValueError):
        return None
    parts = raw.split()
    if not parts:
        return None
    try:
        pid = int(parts[0])
    except ValueError:
        return None
    return pid, mtime


class SerialLock:
    """File-based lock for serialising serial port access.

    Usage::

        lock = SerialLock(timeout=1.0)
        with lock:
            # ... open and write to serial port ...

    If the lock cannot be acquired within *timeout* seconds,
    ``__enter__`` returns ``False`` (instead of raising).  The caller
    should check the return value and skip the write if ``False``.

    Usage with conditional write::

        lock = SerialLock(timeout=1.0)
        with lock as acquired:
            if acquired:
                ser.write(data)
    """

    def __init__(self, timeout: float = 1.0) -> None:
        self.timeout = timeout
        self._fd: int | None = None
        self._acquired = False

    # ── context manager ────────────────────────────────────────────────

    def __enter__(self) -> bool:
        """Try to acquire the lock.  Returns True on success, False on timeout."""
        self._acquired = self._acquire()
        return self._acquired

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._release()

    # ── internals ──────────────────────────────────────────────────────

    def _acquire(self) -> bool:
        acquired = self._try_acquire_once()
        if acquired:
            return True
        # On timeout, check whether the existing lock is orphaned (PID gone
        # and mtime older than our stale threshold). If so, unlink and try
        # once more. A healthy peer is never disturbed.
        if self._steal_if_stale():
            return self._try_acquire_once()
        return False

    def _try_acquire_once(self) -> bool:
        log = get_logger()
        path = _lock_path()
        deadline = time.monotonic() + self.timeout
        poll_interval = 0.02  # 20 ms

        try:
            fd = os.open(path, os.O_CREAT | os.O_RDWR)
        except OSError as exc:
            log.debug("Cannot open lock file %s: %s", path, exc)
            return False

        self._fd = fd

        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt  # noqa: PLC0415

                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl  # noqa: PLC0415

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                self._stamp_lock(fd)
                log.debug("Acquired serial lock: %s", path)
                return True

            except OSError:
                if time.monotonic() >= deadline:
                    log.debug(
                        "Lock timeout (%.1fs) on %s",
                        self.timeout,
                        path,
                    )
                    with contextlib.suppress(OSError):
                        os.close(fd)
                    self._fd = None
                    return False

                time.sleep(poll_interval)

    def _stamp_lock(self, fd: int) -> None:
        """Write ``<pid> <mtime>`` to the lock file so stale detection works."""
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            with contextlib.suppress(OSError):
                os.ftruncate(fd, 0)
            payload = f"{os.getpid()} {time.time():.3f}".encode()
            os.write(fd, payload)
        except OSError:
            pass  # best-effort — stamping failure is non-fatal

    def _steal_if_stale(self) -> bool:
        log = get_logger()
        path = _lock_path()
        stamp = _read_lock_stamp(path)
        if stamp is None:
            return False
        pid, mtime = stamp
        age = max(0.0, time.time() - mtime)
        min_age = max(self.timeout * STALE_LOCK_MULTIPLIER, STALE_LOCK_MIN_AGE)
        if age < min_age:
            return False
        if _pid_is_alive(pid):
            return False
        try:
            os.unlink(path)
        except OSError as exc:
            log.debug("Could not remove stale lock %s: %s", path, exc)
            return False
        log.debug(
            "Removed stale serial lock (pid=%d age=%.1fs): %s",
            pid,
            age,
            path,
        )
        return True

    def _release(self) -> None:
        if self._fd is None:
            return

        log = get_logger()
        fd = self._fd
        self._fd = None
        self._acquired = False

        try:
            if sys.platform == "win32":
                import msvcrt  # noqa: PLC0415

                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl  # noqa: PLC0415

                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass  # best-effort unlock

        with contextlib.suppress(OSError):
            os.close(fd)

        log.debug("Released serial lock")
