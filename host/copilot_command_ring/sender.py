# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Serial sender — send JSON-line messages to the device."""

from __future__ import annotations

import os
import sys
import tempfile

from .config import Config
from .constants import (
    CONSECUTIVE_FAILURE_THRESHOLD,
    DEFAULT_SERIAL_OPEN_TIMEOUT,
    DEFAULT_SERIAL_WRITE_TIMEOUT,
    FAILURE_COUNTER_FILENAME,
)
from .detect_ports import detect_serial_port
from .logging_util import get_logger
from .protocol import format_message_for_log, serialize_message
from .serial_lock import SerialLock

try:
    import serial
except ImportError:
    serial = None  # type: ignore[assignment]


def _failure_counter_path() -> str:
    return os.path.join(tempfile.gettempdir(), FAILURE_COUNTER_FILENAME)


def _read_failure_count() -> int:
    try:
        with open(_failure_counter_path(), encoding="utf-8") as fh:
            return max(0, int(fh.read().strip() or "0"))
    except (OSError, ValueError):
        return 0


def _write_failure_count(count: int) -> None:
    try:
        with open(_failure_counter_path(), "w", encoding="utf-8") as fh:
            fh.write(str(max(0, count)))
    except OSError:
        pass  # best-effort; never block the hook


def _record_failure() -> None:
    """Persist a consecutive-failure counter across hook invocations.

    Each hook is a separate process, so the counter is stored in a small
    file in the system temp directory. On the threshold-th consecutive
    failure we emit a single stderr WARNING; callers still see all
    failures at DEBUG level via the logger.
    """
    count = _read_failure_count() + 1
    _write_failure_count(count)
    if count == CONSECUTIVE_FAILURE_THRESHOLD:
        sys.stderr.write(
            "[copilot-command-ring] WARNING: "
            f"{count} consecutive send failures — ring may be offline. "
            "Run with COPILOT_RING_LOG_LEVEL=DEBUG for details.\n",
        )


def _record_success() -> None:
    if _read_failure_count() != 0:
        _write_failure_count(0)


def send_event(config: Config, message: dict[str, object]) -> bool:
    """Send a JSON-line message to the device over serial.

    Returns ``True`` on success (including dry-run), ``False`` on failure.
    Failures are logged at DEBUG level and never raise — the hook must not
    block or crash the Copilot CLI. After several consecutive failures a
    single stderr WARNING is emitted so silent breakage becomes visible
    without changing the default log level.
    """
    log = get_logger()

    # Carry idle_mode on every outgoing message so the firmware can honor
    # the user's preference when sessions end or go silent. Injected here
    # (rather than in events.py) because this is where Config is in scope
    # and the write is stateless — every hook invocation tags its own line.
    if "idle_mode" not in message:
        message = {**message, "idle_mode": config.idle_mode}

    if config.dry_run:
        log.info("[dry-run] %s", format_message_for_log(message))
        return True

    if serial is None:
        log.debug("pyserial is not installed; cannot send")
        _record_failure()
        return False

    port = detect_serial_port(config)
    if port is None:
        log.debug("No serial port detected; skipping send")
        _record_failure()
        return False

    data = serialize_message(message)

    lock = SerialLock(timeout=config.lock_timeout)
    with lock as acquired:
        if not acquired:
            log.debug("Could not acquire serial lock; skipping send")
            _record_failure()
            return False

        try:
            with serial.Serial(
                port,
                baudrate=config.baud,
                timeout=DEFAULT_SERIAL_OPEN_TIMEOUT,
                write_timeout=DEFAULT_SERIAL_WRITE_TIMEOUT,
            ) as ser:
                ser.write(data)
        except (
            serial.SerialException,
            serial.SerialTimeoutException,
            OSError,
        ) as exc:
            log.debug("Serial send failed on %s: %s", port, exc)
            _record_failure()
            return False

    log.debug("Sent to %s: %s", port, format_message_for_log(message))
    _record_success()
    return True
