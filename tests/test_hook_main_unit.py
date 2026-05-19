# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Unit tests for hook_main — in-process with mocked I/O and sender."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from copilot_command_ring.hook_main import main


class TestHookMainMissingArgs:
    """Missing event name and no ``hook_event_name`` in payload should exit 1."""

    def test_exits_with_code_1_when_argv_and_payload_both_missing(self) -> None:
        with (
            patch("sys.argv", ["hook_main"]),
            patch("sys.stdin", io.StringIO("{}")),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_exits_with_code_1_when_argv_missing_and_payload_invalid(self) -> None:
        with (
            patch("sys.argv", ["hook_main"]),
            patch("sys.stdin", io.StringIO("{not valid json")),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_exits_with_code_1_when_argv_empty_and_payload_event_blank(self) -> None:
        with (
            patch("sys.argv", ["hook_main", ""]),
            patch("sys.stdin", io.StringIO('{"hook_event_name": ""}')),
            pytest.raises(SystemExit, match="1"),
        ):
            main()


class TestHookMainPayloadEventFallback:
    """VS Code-compatible configs supply the event name in the stdin payload.

    Cross-tool configurations (e.g. ``.claude/settings.json``) may invoke
    the wrapper without an argv event name and rely on the documented
    ``hook_event_name`` field in every VS Code-compatible payload.
    """

    def test_payload_hook_event_name_used_when_argv_missing(self) -> None:
        mock_send = MagicMock(return_value=True)
        payload = '{"hook_event_name": "SessionStart", "session_id": "abc"}'
        with (
            patch("sys.argv", ["hook_main"]),
            patch("sys.stdin", io.StringIO(payload)),
            patch("copilot_command_ring.hook_main.send_event", mock_send),
            patch("copilot_command_ring.hook_main.load_config"),
            pytest.raises(SystemExit, match="0"),
        ):
            main()

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        # PascalCase alias resolves to the canonical state; original name
        # preserved on the wire.
        assert msg["event"] == "SessionStart"
        assert msg["state"] == "session_start"
        assert msg["session"] == "abc"

    def test_argv_event_takes_precedence_over_payload_event(self) -> None:
        """If both are supplied, argv wins — argv is how Copilot CLI invokes us."""
        mock_send = MagicMock(return_value=True)
        payload = '{"hook_event_name": "PreToolUse", "tool_name": "bash"}'
        with (
            patch("sys.argv", ["hook_main", "sessionStart"]),
            patch("sys.stdin", io.StringIO(payload)),
            patch("copilot_command_ring.hook_main.send_event", mock_send),
            patch("copilot_command_ring.hook_main.load_config"),
            pytest.raises(SystemExit, match="0"),
        ):
            main()

        msg = mock_send.call_args[0][1]
        assert msg["event"] == "sessionStart"

    def test_vscode_pretooluse_payload_routes_without_argv(self) -> None:
        mock_send = MagicMock(return_value=True)
        payload = (
            '{"hook_event_name": "PreToolUse", "tool_name": "bash", '
            '"tool_input": {"cmd": "ls"}}'
        )
        with (
            patch("sys.argv", ["hook_main"]),
            patch("sys.stdin", io.StringIO(payload)),
            patch("copilot_command_ring.hook_main.send_event", mock_send),
            patch("copilot_command_ring.hook_main.load_config"),
            pytest.raises(SystemExit, match="0"),
        ):
            main()

        msg = mock_send.call_args[0][1]
        assert msg["event"] == "PreToolUse"
        assert msg["state"] == "working"
        assert msg["tool"] == "bash"


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
