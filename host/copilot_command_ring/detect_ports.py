# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Serial port auto-detection."""

from __future__ import annotations

from .config import Config
from .logging_util import get_logger


def _match_port(description: str, patterns: list[str]) -> str | None:
    """Return the first pattern that matches *description* (case-insensitive).

    Returns ``None`` if no pattern matches.
    """
    desc_lower = description.lower()
    for pattern in patterns:
        if pattern.lower() in desc_lower:
            return pattern
    return None


def detect_serial_port(config: Config) -> str | None:
    """Return the serial port device path to use, or ``None``.

    Selection priority:
    1. ``config.serial_port`` — explicit override, returned as-is.
    2. Auto-detect by scanning ``serial.tools.list_ports`` against
       ``config.device_match_descriptions``.
    3. ``None`` if nothing matched (caller handles gracefully).
    """
    log = get_logger()

    if config.serial_port:
        log.debug("Using explicit serial port: %s", config.serial_port)
        return config.serial_port

    try:
        from serial.tools.list_ports import comports  # noqa: PLC0415
    except ImportError:
        log.debug(
            "pyserial is not installed; serial port auto-detection unavailable",
        )
        return None

    try:
        ports = list(comports())
    except Exception:  # noqa: BLE001
        log.debug("Failed to enumerate serial ports", exc_info=True)
        return None

    log.debug("Discovered %d serial port(s)", len(ports))

    for port in ports:
        log.debug(
            "  port=%s  description=%s",
            port.device,
            port.description,
        )
        matched = _match_port(port.description, config.device_match_descriptions)
        if matched is not None:
            log.debug(
                "Matched port %s (description contains %r)",
                port.device,
                matched,
            )
            return port.device

    log.debug(
        "No serial port matched device_match_descriptions=%s",
        config.device_match_descriptions,
    )
    return None
