# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Serial port auto-detection."""

from __future__ import annotations

import re

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


def _usb_interface_number(port: object) -> int:
    """Extract the USB interface number from a pyserial ``ListPortInfo``.

    CircuitPython boards with both console and data CDC channels expose
    two COM ports with the same VID:PID.  The data channel (which the
    firmware reads via ``usb_cdc.data``) is always the higher-numbered
    USB interface.  On Windows the LOCATION string ends with ``x.N``
    where N is the interface number.

    Returns ``0`` when the interface number cannot be determined.
    """
    location = getattr(port, "location", None) or ""
    match = re.search(r"\.(\d+)$", location)
    if match:
        return int(match.group(1))
    return 0


def detect_serial_port(config: Config) -> str | None:
    """Return the serial port device path to use, or ``None``.

    Selection priority:
    1. ``config.serial_port`` — explicit override, returned as-is.
    2. Auto-detect by scanning ``serial.tools.list_ports`` against
       ``config.device_match_descriptions``.  When multiple ports share
       the same VID:PID (e.g. CircuitPython console + data), the port
       with the highest USB interface number is preferred (data channel).
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

    candidates = []
    for port in ports:
        log.debug(
            "  port=%s  description=%s  location=%s",
            port.device,
            port.description,
            getattr(port, "location", ""),
        )
        matched = _match_port(port.description, config.device_match_descriptions)
        if matched is not None:
            candidates.append((port, matched))

    if not candidates:
        log.debug(
            "No serial port matched device_match_descriptions=%s",
            config.device_match_descriptions,
        )
        return None

    # When multiple ports match with the same VID:PID, prefer the one with
    # the highest USB interface number — that is the data channel on
    # CircuitPython boards with dual CDC (console + data).
    best = max(candidates, key=lambda c: _usb_interface_number(c[0]))
    port, matched = best
    log.debug(
        "Selected port %s (description contains %r, interface=%d)",
        port.device,
        matched,
        _usb_interface_number(port),
    )
    return port.device
