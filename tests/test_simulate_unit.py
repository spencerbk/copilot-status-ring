# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Unit tests for the simulation tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from copilot_command_ring.config import Config
from copilot_command_ring.simulate import DEFAULT_SEQUENCE, main, run_sequence


def _make_config(**overrides: object) -> Config:
    defaults: dict[str, object] = {
        "serial_port": None,
        "baud": 115200,
        "brightness": 0.04,
        "dry_run": True,
    }
    defaults.update(overrides)
    return Config(**defaults)  # type: ignore[arg-type]


class TestRunSequence:
    """run_sequence sends all events and sleeps between them."""

    def test_sends_all_events(self) -> None:
        config = _make_config()
        sequence = [
            ("sessionStart", {}),
            ("preToolUse", {"toolName": "bash"}),
            ("sessionEnd", {"reason": "done"}),
        ]
        mock_send = MagicMock(return_value=True)
        with (
            patch("copilot_command_ring.simulate.send_event", mock_send),
            patch("copilot_command_ring.simulate.time"),
        ):
            run_sequence(config, sequence, delay=0.0)

        assert mock_send.call_count == 3

    def test_sleeps_between_events(self) -> None:
        config = _make_config()
        sequence = [
            ("sessionStart", {}),
            ("sessionEnd", {}),
        ]
        mock_time = MagicMock()
        with (
            patch("copilot_command_ring.simulate.send_event", return_value=True),
            patch("copilot_command_ring.simulate.time", mock_time),
        ):
            run_sequence(config, sequence, delay=0.5)

        # Sleep called once between two events (not after the last)
        mock_time.sleep.assert_called_once_with(0.5)

    def test_no_sleep_after_last_event(self) -> None:
        config = _make_config()
        sequence = [("sessionStart", {})]
        mock_time = MagicMock()
        with (
            patch("copilot_command_ring.simulate.send_event", return_value=True),
            patch("copilot_command_ring.simulate.time", mock_time),
        ):
            run_sequence(config, sequence, delay=1.0)

        mock_time.sleep.assert_not_called()

    def test_prints_status_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        config = _make_config()
        sequence = [("sessionStart", {})]
        with (
            patch("copilot_command_ring.simulate.send_event", return_value=True),
            patch("copilot_command_ring.simulate.time"),
        ):
            run_sequence(config, sequence, delay=0.0)

        captured = capsys.readouterr()
        assert "sessionStart" in captured.err
        assert "ok" in captured.err

    def test_reports_failure_status(self, capsys: pytest.CaptureFixture[str]) -> None:
        config = _make_config()
        sequence = [("sessionStart", {})]
        with (
            patch("copilot_command_ring.simulate.send_event", return_value=False),
            patch("copilot_command_ring.simulate.time"),
        ):
            run_sequence(config, sequence, delay=0.0)

        captured = capsys.readouterr()
        assert "FAIL" in captured.err


class TestSimulateMain:
    """simulate.main() parses CLI args and delegates to run_sequence."""

    def test_dry_run_flag_sets_config(self) -> None:
        mock_run = MagicMock()
        with (
            patch("sys.argv", ["simulate", "--dry-run", "--delay", "0"]),
            patch("copilot_command_ring.simulate.run_sequence", mock_run),
            patch(
                "copilot_command_ring.simulate.load_config",
                return_value=_make_config(dry_run=False),
            ),
        ):
            main()

        config_arg = mock_run.call_args[0][0]
        assert config_arg.dry_run is True

    def test_custom_delay(self) -> None:
        mock_run = MagicMock()
        with (
            patch("sys.argv", ["simulate", "--delay", "0.25"]),
            patch("copilot_command_ring.simulate.run_sequence", mock_run),
            patch("copilot_command_ring.simulate.load_config", return_value=_make_config()),
        ):
            main()

        assert mock_run.call_args[1]["delay"] == 0.25 or mock_run.call_args[0][2] == 0.25

    def test_uses_default_sequence(self) -> None:
        mock_run = MagicMock()
        with (
            patch("sys.argv", ["simulate", "--dry-run", "--delay", "0"]),
            patch("copilot_command_ring.simulate.run_sequence", mock_run),
            patch("copilot_command_ring.simulate.load_config", return_value=_make_config()),
        ):
            main()

        sequence_arg = mock_run.call_args[0][1]
        assert sequence_arg is DEFAULT_SEQUENCE

    def test_prints_start_and_end_messages(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("sys.argv", ["simulate", "--dry-run", "--delay", "0"]),
            patch("copilot_command_ring.simulate.run_sequence"),
            patch("copilot_command_ring.simulate.load_config", return_value=_make_config()),
        ):
            main()

        captured = capsys.readouterr()
        assert "Starting simulation" in captured.err
        assert "Simulation complete" in captured.err
