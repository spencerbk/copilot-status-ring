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
    assert result["event"] == "sessionStart"
    assert result["state"] == "session_start"


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
    assert result["event"] == "userPromptSubmitted"
    assert result["state"] == "prompt_submitted"


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
    assert result["state"] == "working"
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


# ── notification (elicitation_dialog) ─────────────────────────────────────


def test_normalize_elicitation_dialog_promotes_to_persistent_state():
    result = normalize_event(
        "notification",
        {"notification_type": "elicitation_dialog", "message": "Choose an option"},
    )
    assert result["event"] == "notification"
    assert result["state"] == "awaiting_elicitation"
    assert result["notification_type"] == "elicitation_dialog"
    assert result["message"] == "Choose an option"


def test_normalize_elicitation_dialog_carries_ttl():
    result = normalize_event(
        "notification",
        {"notification_type": "elicitation_dialog"},
    )
    assert result["state"] == "awaiting_elicitation"
    assert isinstance(result["ttl_s"], int)
    assert result["ttl_s"] == 600


def test_normalize_non_elicitation_notification_stays_notify():
    """Non-elicitation notification types remain transient ``notify``."""
    result = normalize_event(
        "notification",
        {"notification_type": "info", "message": "Done"},
    )
    assert result["state"] == "notify"
    assert "ttl_s" not in result


# ── Unknown event ─────────────────────────────────────────────────────────


def test_normalize_unknown_event_falls_back_to_idle():
    result = normalize_event("totallyUnknownEvent", {"foo": "bar"})
    assert result["event"] == "totallyUnknownEvent"
    assert result["state"] == "idle"


# ── Cross-cutting: session field ─────────────────────────────────────────


def test_normalize_includes_session_when_env_set(monkeypatch: pytest.MonkeyPatch):
    """When COPILOT_RING_CLI_PID is set, every message includes a session field."""
    monkeypatch.setenv("COPILOT_RING_CLI_PID", "42")
    result = normalize_event("preToolUse", {"toolName": "edit"})
    assert result["session"] == "42"


def test_normalize_omits_session_when_env_unset(monkeypatch: pytest.MonkeyPatch):
    """When COPILOT_RING_CLI_PID is not set, no session field appears."""
    monkeypatch.delenv("COPILOT_RING_CLI_PID", raising=False)
    result = normalize_event("preToolUse", {"toolName": "edit"})
    assert "session" not in result


def test_normalize_session_field_across_all_events(monkeypatch: pytest.MonkeyPatch):
    """Session field is added to every event type when the env var is present."""
    monkeypatch.setenv("COPILOT_RING_CLI_PID", "9999")
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
        assert result.get("session") == "9999", f"{event}: missing session field"


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


# ── Cross-cutting: per-state ttl_s defaults ──────────────────────────────


def test_working_state_carries_ttl():
    result = normalize_event("preToolUse", {"toolName": "edit"})
    assert result["state"] == "working"
    assert isinstance(result["ttl_s"], int)
    assert result["ttl_s"] > 0


def test_awaiting_permission_has_longer_ttl_than_working():
    from copilot_command_ring.constants import STATE_TTL_DEFAULTS

    assert STATE_TTL_DEFAULTS["awaiting_permission"] >= STATE_TTL_DEFAULTS["working"]


def test_agent_idle_has_no_ttl():
    result = normalize_event("agentStop", {})
    assert result["state"] == "agent_idle"
    assert "ttl_s" not in result


def test_session_end_has_no_ttl():
    result = normalize_event("sessionEnd", {})
    assert result["state"] == "off"
    assert "ttl_s" not in result


def test_transient_states_have_no_ttl():
    ok = normalize_event("postToolUse", {"toolName": "edit"})
    assert ok["state"] == "tool_ok"
    assert "ttl_s" not in ok

    notify = normalize_event("notification", {})
    assert notify["state"] == "notify"
    assert "ttl_s" not in notify
