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


class TestQuietMode:
    """--quiet suppresses per-event chatter for the setup-wizard validation step."""

    def test_run_sequence_quiet_suppresses_per_event_lines(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = _make_config()
        sequence = [
            ("sessionStart", {}),
            ("preToolUse", {"toolName": "bash"}),
            ("sessionEnd", {}),
        ]
        with (
            patch("copilot_command_ring.simulate.send_event", return_value=True),
            patch("copilot_command_ring.simulate.time"),
        ):
            failures = run_sequence(config, sequence, delay=0.0, quiet=True)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "sessionStart" not in captured.err
        assert "[1/3]" not in captured.err
        assert "[2/3]" not in captured.err
        assert "[3/3]" not in captured.err
        assert failures == 0

    def test_run_sequence_quiet_returns_failure_count(self) -> None:
        config = _make_config()
        sequence = [("sessionStart", {}), ("sessionEnd", {})]

        # First call ok, second call fails. send_event(config, message) is invoked
        # once per event, so set side_effect to control per-event outcomes.
        with (
            patch(
                "copilot_command_ring.simulate.send_event",
                side_effect=[True, False],
            ),
            patch("copilot_command_ring.simulate.time"),
        ):
            failures = run_sequence(config, sequence, delay=0.0, quiet=True)

        assert failures == 1

    def test_main_quiet_skips_banner_and_uses_summary_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch("sys.argv", ["simulate", "--dry-run", "--delay", "0", "--quiet"]),
            patch(
                "copilot_command_ring.simulate.run_sequence",
                return_value=0,
            ),
            patch("copilot_command_ring.simulate.load_config", return_value=_make_config()),
        ):
            main()

        captured = capsys.readouterr()
        assert "Starting simulation" not in captured.err
        assert "Simulation complete" in captured.err
        # The summary surfaces total events and failure count on a single line.
        assert f"{len(DEFAULT_SEQUENCE)} events" in captured.err
        assert "ok" in captured.err

    def test_main_quiet_surfaces_failure_count(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch("sys.argv", ["simulate", "--dry-run", "--delay", "0", "--quiet"]),
            patch(
                "copilot_command_ring.simulate.run_sequence",
                return_value=3,
            ),
            patch("copilot_command_ring.simulate.load_config", return_value=_make_config()),
        ):
            main()

        captured = capsys.readouterr()
        assert "3 failed" in captured.err
