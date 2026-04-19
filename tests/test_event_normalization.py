# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for copilot_command_ring.events.normalize_event."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from copilot_command_ring.events import normalize_event

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── sessionStart ──────────────────────────────────────────────────────────


def test_normalize_session_start_empty_payload():
    result = normalize_event("sessionStart", {})
    assert result == {"event": "sessionStart", "state": "session_start"}


def test_normalize_session_start_with_payload():
    payload = _load_fixture("sessionStart.json")
    result = normalize_event("sessionStart", payload)
    assert result["event"] == "sessionStart"
    assert result["state"] == "session_start"


# ── sessionEnd ────────────────────────────────────────────────────────────


def test_normalize_session_end_includes_reason():
    payload = _load_fixture("sessionEnd.json")
    result = normalize_event("sessionEnd", payload)
    assert result["event"] == "sessionEnd"
    assert result["state"] == "off"
    assert result["reason"] == "user_exit"


def test_normalize_session_end_empty_payload_omits_reason():
    result = normalize_event("sessionEnd", {})
    assert result["event"] == "sessionEnd"
    assert "reason" not in result


# ── userPromptSubmitted ───────────────────────────────────────────────────


def test_normalize_user_prompt_submitted_state():
    payload = _load_fixture("userPromptSubmitted.json")
    result = normalize_event("userPromptSubmitted", payload)
    assert result == {"event": "userPromptSubmitted", "state": "prompt_submitted"}


# ── preToolUse ────────────────────────────────────────────────────────────


def test_normalize_pre_tool_use_extracts_tool():
    payload = _load_fixture("preToolUse.json")
    result = normalize_event("preToolUse", payload)
    assert result["state"] == "working"
    assert result["tool"] == "edit"


def test_normalize_pre_tool_use_empty_payload_omits_tool():
    result = normalize_event("preToolUse", {})
    assert result["state"] == "working"
    assert "tool" not in result


# ── postToolUse ───────────────────────────────────────────────────────────


def test_normalize_post_tool_use_extracts_tool_and_result():
    payload = _load_fixture("postToolUse.json")
    result = normalize_event("postToolUse", payload)
    assert result["state"] == "tool_ok"
    assert result["tool"] == "read_file"
    assert result["result"] == "success"


def test_normalize_post_tool_use_missing_tool_result():
    result = normalize_event("postToolUse", {"toolName": "edit"})
    assert result["tool"] == "edit"
    assert "result" not in result


def test_normalize_post_tool_use_non_dict_tool_result():
    result = normalize_event("postToolUse", {"toolName": "x", "toolResult": "string"})
    assert result["tool"] == "x"
    assert "result" not in result


# ── postToolUseFailure ────────────────────────────────────────────────────


def test_normalize_post_tool_use_failure_extracts_tool_and_error():
    payload = _load_fixture("postToolUseFailure.json")
    result = normalize_event("postToolUseFailure", payload)
    assert result["state"] == "tool_error"
    assert result["tool"] == "bash"
    assert result["error"] == "Command exited with code 1"


def test_normalize_post_tool_use_failure_empty_payload():
    result = normalize_event("postToolUseFailure", {})
    assert result["state"] == "tool_error"
    assert "tool" not in result
    assert "error" not in result


# ── permissionRequest ─────────────────────────────────────────────────────


def test_normalize_permission_request_extracts_tool():
    payload = _load_fixture("permissionRequest.json")
    result = normalize_event("permissionRequest", payload)
    assert result["state"] == "awaiting_permission"
    assert result["tool"] == "bash"


# ── subagentStart ─────────────────────────────────────────────────────────


def test_normalize_subagent_start_extracts_agent():
    payload = _load_fixture("subagentStart.json")
    result = normalize_event("subagentStart", payload)
    assert result["state"] == "subagent_active"
    assert result["agent"] == "code-review"


# ── subagentStop ──────────────────────────────────────────────────────────


def test_normalize_subagent_stop_extracts_agent():
    payload = _load_fixture("subagentStop.json")
    result = normalize_event("subagentStop", payload)
    assert result["state"] == "idle"
    assert result["agent"] == "code-review"


# ── agentStop ─────────────────────────────────────────────────────────────


def test_normalize_agent_stop_extracts_reason():
    payload = _load_fixture("agentStop.json")
    result = normalize_event("agentStop", payload)
    assert result["state"] == "agent_idle"
    assert result["reason"] == "completed"


def test_normalize_agent_stop_empty_payload_omits_reason():
    result = normalize_event("agentStop", {})
    assert result["state"] == "agent_idle"
    assert "reason" not in result


# ── preCompact ────────────────────────────────────────────────────────────


def test_normalize_pre_compact_extracts_trigger():
    payload = _load_fixture("preCompact.json")
    result = normalize_event("preCompact", payload)
    assert result["state"] == "compacting"
    assert result["trigger"] == "context_overflow"


# ── errorOccurred ─────────────────────────────────────────────────────────


def test_normalize_error_occurred_extracts_nested_error():
    payload = _load_fixture("errorOccurred.json")
    result = normalize_event("errorOccurred", payload)
    assert result["state"] == "error"
    assert result["error"] == "RateLimitError"
    assert result["message"] == "API rate limit exceeded"
    assert result["recoverable"] is True
    assert result["errorContext"] == "model_request"


def test_normalize_error_occurred_non_dict_error():
    result = normalize_event("errorOccurred", {"error": "plain string"})
    assert result["state"] == "error"
    assert "error" not in result  # string error is not a dict, so name not extracted


def test_normalize_error_occurred_empty_payload():
    result = normalize_event("errorOccurred", {})
    assert result["state"] == "error"
    assert "error" not in result
    assert "recoverable" not in result


# ── notification ──────────────────────────────────────────────────────────


def test_normalize_notification_extracts_type():
    result = normalize_event(
        "notification",
        {"notification_type": "info", "message": "Done"},
    )
    assert result["state"] == "notify"
    assert result["notification_type"] == "info"
    assert result["message"] == "Done"


def test_normalize_notification_empty_payload():
    result = normalize_event("notification", {})
    assert result["state"] == "notify"
    assert "notification_type" not in result
    assert "message" not in result


# ── Unknown event ─────────────────────────────────────────────────────────


def test_normalize_unknown_event_falls_back_to_idle():
    result = normalize_event("totallyUnknownEvent", {"foo": "bar"})
    assert result["event"] == "totallyUnknownEvent"
    assert result["state"] == "idle"


# ── Cross-cutting: no None values ────────────────────────────────────────


def test_normalize_never_includes_none_values():
    """Every known event with an empty payload should produce no None values."""
    events = [
        "sessionStart",
        "sessionEnd",
        "userPromptSubmitted",
        "preToolUse",
        "postToolUse",
        "postToolUseFailure",
        "permissionRequest",
        "subagentStart",
        "subagentStop",
        "agentStop",
        "preCompact",
        "errorOccurred",
        "notification",
    ]
    for event in events:
        result = normalize_event(event, {})
        for key, value in result.items():
            assert value is not None, f"{event}: key '{key}' is None"


# ── Cross-cutting: empty payload never crashes ───────────────────────────


@pytest.mark.parametrize(
    "event_name",
    [
        "sessionStart",
        "sessionEnd",
        "userPromptSubmitted",
        "preToolUse",
        "postToolUse",
        "postToolUseFailure",
        "permissionRequest",
        "subagentStart",
        "subagentStop",
        "agentStop",
        "preCompact",
        "errorOccurred",
        "notification",
    ],
)
def test_normalize_empty_payload_does_not_crash(event_name: str):
    result = normalize_event(event_name, {})
    assert isinstance(result, dict)
    assert result["event"] == event_name
