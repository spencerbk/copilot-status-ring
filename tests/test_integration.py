# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Integration tests — pipe fixture JSON through hook_main end-to-end."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST_DIR = REPO_ROOT / "host"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _run_hook(
    event_name: str,
    payload: dict | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Invoke hook_main as a subprocess, returning the result."""
    env = {
        "PYTHONPATH": str(HOST_DIR),
        "COPILOT_RING_DRY_RUN": "1",
        "COPILOT_RING_LOG_LEVEL": "DEBUG",
        "SYSTEMROOT": "",  # needed on Windows for subprocess
    }
    # Preserve PATH and essential env
    import os

    for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOMEDRIVE", "HOMEPATH"):
        if key in os.environ:
            env[key] = os.environ[key]
    if extra_env:
        env.update(extra_env)

    stdin_data = json.dumps(payload or {})
    return subprocess.run(
        [sys.executable, "-m", "copilot_command_ring.hook_main", event_name],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


class TestHookMainIntegration:
    """End-to-end tests piping payloads through hook_main."""

    def test_session_start_exits_cleanly(self) -> None:
        result = _run_hook("sessionStart")
        assert result.returncode == 0

    def test_stdout_is_empty(self) -> None:
        """stdout must remain empty — Copilot interprets it as control JSON."""
        result = _run_hook("preToolUse", {"toolName": "edit"})
        assert result.stdout == ""

    def test_permission_request_stdout_empty(self) -> None:
        """permissionRequest is especially sensitive to stdout."""
        result = _run_hook("permissionRequest", {"toolName": "bash"})
        assert result.stdout == ""

    def test_dry_run_logs_to_stderr(self) -> None:
        result = _run_hook("preToolUse", {"toolName": "bash"})
        assert "[dry-run]" in result.stderr

    def test_all_events_exit_zero(self) -> None:
        events = [
            ("sessionStart", {}),
            ("sessionEnd", {"reason": "user_exit"}),
            ("userPromptSubmitted", {}),
            ("preToolUse", {"toolName": "edit"}),
            ("postToolUse", {"toolName": "edit", "toolResult": {"resultType": "success"}}),
            ("postToolUseFailure", {"toolName": "bash", "error": "fail"}),
            ("permissionRequest", {"toolName": "bash"}),
            ("subagentStart", {"agentName": "reviewer"}),
            ("subagentStop", {"agentName": "reviewer"}),
            ("agentStop", {"stopReason": "end_turn"}),
            ("preCompact", {"trigger": "auto"}),
            ("errorOccurred", {"error": {"name": "Err", "message": "msg"}, "recoverable": True}),
            (
                "notification",
                {"notification_type": "info", "message": "Agent completed background task"},
            ),
            (
                "notification",
                {"notification_type": "elicitation_dialog", "message": "Choose an option"},
            ),
        ]
        for event_name, payload in events:
            result = _run_hook(event_name, payload)
            assert result.returncode == 0, f"{event_name} exited with {result.returncode}"
            assert result.stdout == "", f"{event_name} wrote to stdout: {result.stdout!r}"

    def test_unknown_event_exits_zero(self) -> None:
        result = _run_hook("unknownEvent", {"foo": "bar"})
        assert result.returncode == 0
        assert result.stdout == ""

    def test_empty_stdin_does_not_crash(self) -> None:
        """Simulate an event with no payload on stdin."""
        result = subprocess.run(
            [sys.executable, "-m", "copilot_command_ring.hook_main", "sessionStart"],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
            env={
                **{k: v for k, v in __import__("os").environ.items()},
                "PYTHONPATH": str(HOST_DIR),
                "COPILOT_RING_DRY_RUN": "1",
            },
        )
        assert result.returncode == 0

    def test_malformed_json_stdin_does_not_crash(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "copilot_command_ring.hook_main", "sessionStart"],
            input="{invalid json",
            capture_output=True,
            text=True,
            timeout=10,
            env={
                **{k: v for k, v in __import__("os").environ.items()},
                "PYTHONPATH": str(HOST_DIR),
                "COPILOT_RING_DRY_RUN": "1",
            },
        )
        assert result.returncode == 0

    def test_fixture_files_roundtrip(self) -> None:
        """Each fixture file should pipe through hook_main without error."""
        fixture_map = {
            "sessionStart.json": "sessionStart",
            "sessionEnd.json": "sessionEnd",
            "preToolUse.json": "preToolUse",
            "postToolUse.json": "postToolUse",
            "postToolUseFailure.json": "postToolUseFailure",
            "permissionRequest.json": "permissionRequest",
            "subagentStart.json": "subagentStart",
            "subagentStop.json": "subagentStop",
            "agentStop.json": "agentStop",
            "preCompact.json": "preCompact",
            "errorOccurred.json": "errorOccurred",
            "notification.json": "notification",
        }
        for filename, event_name in fixture_map.items():
            fixture_path = FIXTURES / filename
            if not fixture_path.exists():
                pytest.skip(f"Fixture {filename} not found")
            payload = json.loads(fixture_path.read_text())
            result = _run_hook(event_name, payload)
            assert result.returncode == 0, f"{filename}: exit {result.returncode}"
            assert result.stdout == "", f"{filename}: stdout={result.stdout!r}"

    def test_notification_dry_run_logs_notify_state(self) -> None:
        result = _run_hook(
            "notification",
            {"notification_type": "info", "message": "Agent completed background task"},
        )
        assert result.returncode == 0
        assert result.stdout == ""
        assert '"state": "notify"' in result.stderr or '"state":"notify"' in result.stderr

    def test_elicitation_dialog_dry_run_logs_awaiting_elicitation(self) -> None:
        """Elicitation dialog notifications produce a persistent state."""
        result = _run_hook(
            "notification",
            {"notification_type": "elicitation_dialog", "message": "Choose"},
        )
        assert result.returncode == 0
        assert result.stdout == ""
        assert (
            '"state": "awaiting_elicitation"' in result.stderr
            or '"state":"awaiting_elicitation"' in result.stderr
        )

    def test_session_field_in_dry_run_output(self) -> None:
        """When COPILOT_RING_CLI_PID is set, the session field appears in output."""
        result = _run_hook(
            "preToolUse",
            {"toolName": "edit"},
            extra_env={"COPILOT_RING_CLI_PID": "12345"},
        )
        assert result.returncode == 0
        assert result.stdout == ""
        assert '"session": "12345"' in result.stderr or '"session":"12345"' in result.stderr

    def test_no_session_field_without_env(self) -> None:
        """Without COPILOT_RING_CLI_PID, no session field in output."""
        result = _run_hook("preToolUse", {"toolName": "edit"})
        assert result.returncode == 0
        assert "session" not in result.stderr
