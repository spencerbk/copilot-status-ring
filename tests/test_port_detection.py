# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for copilot_command_ring.detect_ports (serial port detection)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from copilot_command_ring.config import Config
from copilot_command_ring.detect_ports import detect_serial_port


def _fake_port(device: str, description: str) -> SimpleNamespace:
    """Create a mock serial port info object."""
    return SimpleNamespace(device=device, description=description)


# ── Explicit port in config ───────────────────────────────────────────────


def test_explicit_port_returned_directly():
    cfg = Config(serial_port="COM3")
    result = detect_serial_port(cfg)
    assert result == "COM3"


def test_explicit_port_skips_auto_detect():
    cfg = Config(serial_port="/dev/ttyUSB0")
    with patch("serial.tools.list_ports.comports") as mock_comports:
        mock_comports.side_effect = AssertionError("should not be called")
        result = detect_serial_port(cfg)
    assert result == "/dev/ttyUSB0"
    mock_comports.assert_not_called()


# ── Auto-detect by description ────────────────────────────────────────────


def test_auto_detect_matches_by_description():
    ports = [
        _fake_port("/dev/ttyACM0", "CircuitPython CDC control"),
        _fake_port("/dev/ttyS0", "Standard Serial Port"),
    ]
    cfg = Config(serial_port=None, device_match_descriptions=["CircuitPython"])
    with patch("serial.tools.list_ports.comports", return_value=ports):
        result = detect_serial_port(cfg)
    assert result == "/dev/ttyACM0"


def test_auto_detect_case_insensitive():
    ports = [_fake_port("COM4", "CIRCUITPYTHON USB DEVICE")]
    cfg = Config(serial_port=None, device_match_descriptions=["circuitpython"])
    with patch("serial.tools.list_ports.comports", return_value=ports):
        result = detect_serial_port(cfg)
    assert result == "COM4"


def test_auto_detect_matches_arduino():
    ports = [_fake_port("COM6", "Arduino Mega 2560")]
    cfg = Config(serial_port=None, device_match_descriptions=["Arduino"])
    with patch("serial.tools.list_ports.comports", return_value=ports):
        result = detect_serial_port(cfg)
    assert result == "COM6"


def test_auto_detect_returns_first_match():
    ports = [
        _fake_port("COM1", "Standard Serial"),
        _fake_port("COM2", "Arduino Uno"),
        _fake_port("COM3", "CircuitPython CDC"),
    ]
    cfg = Config(
        serial_port=None,
        device_match_descriptions=["CircuitPython", "Arduino"],
    )
    with patch("serial.tools.list_ports.comports", return_value=ports):
        result = detect_serial_port(cfg)
    # COM2 matches "Arduino" first in the port scan order
    assert result == "COM2"


# ── No match returns None ─────────────────────────────────────────────────


def test_no_match_returns_none():
    ports = [
        _fake_port("COM1", "Bluetooth Serial"),
        _fake_port("COM2", "Intel UART"),
    ]
    cfg = Config(serial_port=None, device_match_descriptions=["CircuitPython"])
    with patch("serial.tools.list_ports.comports", return_value=ports):
        result = detect_serial_port(cfg)
    assert result is None


def test_empty_ports_list_returns_none():
    cfg = Config(serial_port=None, device_match_descriptions=["CircuitPython"])
    with patch("serial.tools.list_ports.comports", return_value=[]):
        result = detect_serial_port(cfg)
    assert result is None


# ── comports failure handled gracefully ───────────────────────────────────


def test_comports_exception_returns_none():
    cfg = Config(serial_port=None)
    with patch("serial.tools.list_ports.comports", side_effect=OSError("USB error")):
        result = detect_serial_port(cfg)
    assert result is None


# ── pyserial not installed ────────────────────────────────────────────────


def test_pyserial_import_error_returns_none():
    """When pyserial is not installed, auto-detect returns None."""
    cfg = Config(serial_port=None)

    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _block_serial_import(name, *args, **kwargs):
        if name == "serial.tools.list_ports":
            raise ImportError("No module named 'serial'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_block_serial_import):
        result = detect_serial_port(cfg)
    assert result is None
