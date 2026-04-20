# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Unit tests for the cross-platform serial lock module."""

from __future__ import annotations

import os
import threading
import time

import pytest
from copilot_command_ring.serial_lock import SerialLock, _lock_path


class TestSerialLockHappyPath:
    """Basic acquire / release cycle."""

    def test_acquire_and_release(self, tmp_path: object) -> None:
        lock = SerialLock(timeout=1.0)
        with lock as acquired:
            assert acquired is True
            # Lock file should exist while held
            assert os.path.exists(_lock_path())

    def test_context_manager_returns_true(self) -> None:
        lock = SerialLock(timeout=1.0)
        with lock as acquired:
            assert acquired is True

    def test_reentrant_sequential(self) -> None:
        """Same process can acquire → release → acquire again."""
        for _ in range(3):
            lock = SerialLock(timeout=1.0)
            with lock as acquired:
                assert acquired is True


class TestSerialLockTimeout:
    """Lock timeout returns False instead of blocking forever."""

    def test_timeout_returns_false(self) -> None:
        # Hold a lock in a background thread, then try to acquire in main
        barrier = threading.Event()
        held = threading.Event()

        def _hold_lock() -> None:
            lock = SerialLock(timeout=2.0)
            with lock:
                held.set()
                barrier.wait(timeout=5.0)

        t = threading.Thread(target=_hold_lock, daemon=True)
        t.start()
        held.wait(timeout=3.0)

        # Now try to acquire with a very short timeout
        lock2 = SerialLock(timeout=0.1)
        with lock2 as acquired:
            assert acquired is False

        barrier.set()
        t.join(timeout=3.0)


class TestSerialLockConcurrency:
    """Two threads contending for the lock — both eventually succeed."""

    def test_sequential_access_under_contention(self) -> None:
        results: list[str] = []
        lock_acquired_count = 0

        def _worker(name: str) -> None:
            nonlocal lock_acquired_count
            lock = SerialLock(timeout=3.0)
            with lock as acquired:
                if acquired:
                    lock_acquired_count += 1
                    results.append(name)
                    time.sleep(0.05)  # hold briefly

        t1 = threading.Thread(target=_worker, args=("A",))
        t2 = threading.Thread(target=_worker, args=("B",))
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        # Both should have acquired (sequentially)
        assert lock_acquired_count == 2
        assert set(results) == {"A", "B"}


class TestSerialLockExceptionSafety:
    """Lock is released even if the body raises an exception."""

    def test_released_on_exception(self) -> None:
        lock = SerialLock(timeout=1.0)
        with pytest.raises(ValueError, match="boom"), lock as acquired:
            assert acquired is True
            raise ValueError("boom")

        # Lock should be released — we can acquire again
        lock2 = SerialLock(timeout=0.5)
        with lock2 as acquired:
            assert acquired is True


class TestSerialLockFilePath:
    """Lock file is in the temp directory."""

    def test_lock_path_in_tempdir(self) -> None:
        import tempfile

        path = _lock_path()
        assert path.startswith(tempfile.gettempdir())
        assert "copilot-command-ring" in path
