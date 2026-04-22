# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Unit tests for the serial sender module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from copilot_command_ring.config import Config
from copilot_command_ring.protocol import serialize_message
from copilot_command_ring.sender import send_event


def _make_config(**overrides: object) -> Config:
    defaults: dict[str, object] = {
        "serial_port": None,
        "baud": 115200,
        "brightness": 0.04,
        "dry_run": False,
    }
    defaults.update(overrides)
    return Config(**defaults)  # type: ignore[arg-type]


SAMPLE_MESSAGE: dict[str, object] = {"event": "sessionStart", "state": "session_start"}


class TestSendEventDryRun:
    """Dry-run mode logs and returns True without touching serial."""

    def test_returns_true(self) -> None:
        config = _make_config(dry_run=True)
        assert send_event(config, SAMPLE_MESSAGE) is True

    def test_does_not_open_serial(self) -> None:
        config = _make_config(dry_run=True)
        with patch("copilot_command_ring.sender.serial") as mock_serial:
            send_event(config, SAMPLE_MESSAGE)
            mock_serial.Serial.assert_not_called()


class TestSendEventNoSerial:
    """When pyserial is not installed, send_event returns False."""

    def test_returns_false(self) -> None:
        config = _make_config()
        with patch("copilot_command_ring.sender.serial", None):
            assert send_event(config, SAMPLE_MESSAGE) is False


class TestSendEventImportFallback:
    """When pyserial cannot be imported, the module sets serial = None."""

    def test_import_error_sets_serial_to_none(self) -> None:
        import importlib

        import copilot_command_ring.sender as sender_mod

        original_serial = sender_mod.serial
        try:
            with patch.dict("sys.modules", {"serial": None}):
                importlib.reload(sender_mod)
            assert sender_mod.serial is None
        finally:
            sender_mod.serial = original_serial
            importlib.reload(sender_mod)


class TestSendEventNoPort:
    """When no serial port is detected, send_event returns False."""

    def test_returns_false(self) -> None:
        config = _make_config()
        with patch("copilot_command_ring.sender.detect_serial_port", return_value=None):
            assert send_event(config, SAMPLE_MESSAGE) is False


class TestSendEventSuccess:
    """Successful serial send returns True and writes correct data."""

    def test_returns_true(self) -> None:
        config = _make_config()
        mock_ser = MagicMock()
        mock_serial_cls = MagicMock()
        mock_serial_cls.__enter__ = MagicMock(return_value=mock_ser)
        mock_serial_cls.__exit__ = MagicMock(return_value=False)

        fake_serial = MagicMock()
        fake_serial.Serial.return_value = mock_serial_cls
        fake_serial.SerialException = OSError
        fake_serial.SerialTimeoutException = OSError

        with (
            patch("copilot_command_ring.sender.serial", fake_serial),
            patch(
                "copilot_command_ring.sender.detect_serial_port",
                return_value="COM7",
            ),
        ):
            result = send_event(config, SAMPLE_MESSAGE)

        assert result is True
        fake_serial.Serial.assert_called_once_with(
            "COM7",
            baudrate=config.baud,
            timeout=0.3,
            write_timeout=0.3,
        )

    def test_writes_serialized_message(self) -> None:
        config = _make_config()
        mock_ser = MagicMock()

        fake_serial = MagicMock()
        fake_serial.Serial.return_value.__enter__ = MagicMock(return_value=mock_ser)
        fake_serial.Serial.return_value.__exit__ = MagicMock(return_value=False)
        fake_serial.SerialException = OSError
        fake_serial.SerialTimeoutException = OSError

        with (
            patch("copilot_command_ring.sender.serial", fake_serial),
            patch(
                "copilot_command_ring.sender.detect_serial_port",
                return_value="COM7",
            ),
        ):
            send_event(config, SAMPLE_MESSAGE)

        expected_data = serialize_message(SAMPLE_MESSAGE)
        mock_ser.write.assert_called_once_with(expected_data)

    def test_uses_configured_lock_timeout(self) -> None:
        config = _make_config(lock_timeout=2.5)
        mock_ser = MagicMock()

        fake_serial = MagicMock()
        fake_serial.Serial.return_value.__enter__ = MagicMock(return_value=mock_ser)
        fake_serial.Serial.return_value.__exit__ = MagicMock(return_value=False)
        fake_serial.SerialException = OSError
        fake_serial.SerialTimeoutException = OSError

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=True)
        mock_lock.__exit__ = MagicMock(return_value=False)

        with (
            patch("copilot_command_ring.sender.serial", fake_serial),
            patch(
                "copilot_command_ring.sender.detect_serial_port",
                return_value="COM7",
            ),
            patch(
                "copilot_command_ring.sender.SerialLock",
                return_value=mock_lock,
            ) as mock_lock_cls,
        ):
            assert send_event(config, SAMPLE_MESSAGE) is True

        mock_lock_cls.assert_called_once_with(timeout=2.5)


class TestSendEventSerialError:
    """Serial errors are caught and return False."""

    def test_serial_exception_returns_false(self) -> None:
        config = _make_config()

        fake_serial = MagicMock()
        fake_serial.Serial.side_effect = OSError("device not found")
        fake_serial.SerialException = OSError
        fake_serial.SerialTimeoutException = OSError

        with (
            patch("copilot_command_ring.sender.serial", fake_serial),
            patch(
                "copilot_command_ring.sender.detect_serial_port",
                return_value="COM7",
            ),
        ):
            assert send_event(config, SAMPLE_MESSAGE) is False

    def test_timeout_returns_false(self) -> None:
        config = _make_config()

        fake_serial = MagicMock()
        fake_serial.Serial.side_effect = OSError("write timeout")
        fake_serial.SerialException = OSError
        fake_serial.SerialTimeoutException = OSError

        with (
            patch("copilot_command_ring.sender.serial", fake_serial),
            patch(
                "copilot_command_ring.sender.detect_serial_port",
                return_value="COM7",
            ),
        ):
            assert send_event(config, SAMPLE_MESSAGE) is False


class TestSendEventLockTimeout:
    """When the serial lock cannot be acquired, send_event returns False."""

    def test_lock_timeout_returns_false(self) -> None:
        config = _make_config()

        fake_serial = MagicMock()
        fake_serial.SerialException = OSError
        fake_serial.SerialTimeoutException = OSError

        mock_lock = MagicMock()
        mock_lock.__enter__ = MagicMock(return_value=False)
        mock_lock.__exit__ = MagicMock(return_value=False)

        with (
            patch("copilot_command_ring.sender.serial", fake_serial),
            patch(
                "copilot_command_ring.sender.detect_serial_port",
                return_value="COM7",
            ),
            patch(
                "copilot_command_ring.sender.SerialLock",
                return_value=mock_lock,
            ),
        ):
            assert send_event(config, SAMPLE_MESSAGE) is False

        fake_serial.Serial.assert_not_called()
