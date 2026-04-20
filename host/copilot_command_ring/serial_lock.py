# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Cross-platform file lock for serialising access to the USB serial port.

When multiple Copilot CLI sessions run on the same machine (across different
repos), their hook processes may try to open the serial port simultaneously.
This module provides a lightweight file lock so that only one process writes
at a time — preventing port-busy errors and byte-level corruption.

The lock file lives in the OS temp directory so it is visible to all processes
regardless of which repo they run from.
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


def _lock_path() -> str:
    """Return the path to the system-wide lock file."""
    return os.path.join(tempfile.gettempdir(), LOCK_FILENAME)


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
        log = get_logger()
        path = _lock_path()
        deadline = time.monotonic() + self.timeout
        poll_interval = 0.02  # 20 ms

        try:
            # Open or create the lock file
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

                log.debug("Acquired serial lock: %s", path)
                return True

            except OSError:
                if time.monotonic() >= deadline:
                    log.debug(
                        "Lock timeout (%.1fs) on %s",
                        self.timeout,
                        path,
                    )
                    # Close the fd since we failed to lock
                    with contextlib.suppress(OSError):
                        os.close(fd)
                    self._fd = None
                    return False

                time.sleep(poll_interval)

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
