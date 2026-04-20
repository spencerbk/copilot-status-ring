# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Serial sender — send JSON-line messages to the device."""

from __future__ import annotations

from .config import Config
from .constants import (
    DEFAULT_SERIAL_OPEN_TIMEOUT,
    DEFAULT_SERIAL_WRITE_TIMEOUT,
)
from .detect_ports import detect_serial_port
from .logging_util import get_logger
from .protocol import format_message_for_log, serialize_message
from .serial_lock import SerialLock

try:
    import serial
except ImportError:
    serial = None  # type: ignore[assignment]


def send_event(config: Config, message: dict[str, object]) -> bool:
    """Send a JSON-line message to the device over serial.

    Returns ``True`` on success (including dry-run), ``False`` on failure.
    Failures are logged at DEBUG level and never raise — the hook must not
    block or crash the Copilot CLI.
    """
    log = get_logger()

    if config.dry_run:
        log.info("[dry-run] %s", format_message_for_log(message))
        return True

    if serial is None:
        log.debug("pyserial is not installed; cannot send")
        return False

    port = detect_serial_port(config)
    if port is None:
        log.debug("No serial port detected; skipping send")
        return False

    data = serialize_message(message)

    lock = SerialLock(timeout=config.lock_timeout)
    with lock as acquired:
        if not acquired:
            log.debug("Could not acquire serial lock; skipping send")
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
            return False

    log.debug("Sent to %s: %s", port, format_message_for_log(message))
    return True
