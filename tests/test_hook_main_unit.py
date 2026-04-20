# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Unit tests for hook_main — in-process with mocked I/O and sender."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from copilot_command_ring.hook_main import main


class TestHookMainMissingArgs:
    """Missing event name argument should exit with code 1."""

    def test_exits_with_code_1(self) -> None:
        with (
            patch("sys.argv", ["hook_main"]),
            pytest.raises(SystemExit, match="1"),
        ):
            main()


class TestHookMainValidEvent:
    """Valid event name triggers normalize + send_event."""

    def test_calls_send_event(self) -> None:
        mock_send = MagicMock(return_value=True)
        with (
            patch("sys.argv", ["hook_main", "sessionStart"]),
            patch("sys.stdin", io.StringIO("{}")),
            patch("copilot_command_ring.hook_main.send_event", mock_send),
            patch("copilot_command_ring.hook_main.load_config"),
            pytest.raises(SystemExit, match="0"),
        ):
            main()

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        assert msg["event"] == "sessionStart"

    def test_passes_payload_to_normalize(self) -> None:
        mock_send = MagicMock(return_value=True)
        payload = '{"toolName": "bash"}'
        with (
            patch("sys.argv", ["hook_main", "preToolUse"]),
            patch("sys.stdin", io.StringIO(payload)),
            patch("copilot_command_ring.hook_main.send_event", mock_send),
            patch("copilot_command_ring.hook_main.load_config"),
            pytest.raises(SystemExit, match="0"),
        ):
            main()

        msg = mock_send.call_args[0][1]
        assert msg["event"] == "preToolUse"
        assert msg["tool"] == "bash"


class TestHookMainBadStdin:
    """Malformed or empty stdin should not crash — uses empty payload."""

    def test_malformed_json_uses_empty_payload(self) -> None:
        mock_send = MagicMock(return_value=True)
        with (
            patch("sys.argv", ["hook_main", "sessionStart"]),
            patch("sys.stdin", io.StringIO("{not valid json")),
            patch("copilot_command_ring.hook_main.send_event", mock_send),
            patch("copilot_command_ring.hook_main.load_config"),
            pytest.raises(SystemExit, match="0"),
        ):
            main()

        mock_send.assert_called_once()

    def test_empty_stdin_uses_empty_payload(self) -> None:
        mock_send = MagicMock(return_value=True)
        with (
            patch("sys.argv", ["hook_main", "sessionStart"]),
            patch("sys.stdin", io.StringIO("")),
            patch("copilot_command_ring.hook_main.send_event", mock_send),
            patch("copilot_command_ring.hook_main.load_config"),
            pytest.raises(SystemExit, match="0"),
        ):
            main()

        mock_send.assert_called_once()


class TestHookMainUnexpectedException:
    """Unexpected errors are logged, not raised."""

    def test_exception_does_not_propagate(self) -> None:
        with (
            patch("sys.argv", ["hook_main", "sessionStart"]),
            patch("sys.stdin", io.StringIO("{}")),
            patch(
                "copilot_command_ring.hook_main.load_config",
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(SystemExit, match="0"),
        ):
            main()
