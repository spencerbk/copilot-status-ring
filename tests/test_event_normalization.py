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


def test_normalize_session_start_extracts_source():
    result = normalize_event("sessionStart", {"source": "resume"})
    assert result["source"] == "resume"


def test_normalize_session_start_source_new():
    result = normalize_event("sessionStart", {"source": "new"})
    assert result["source"] == "new"


def test_normalize_session_start_missing_source_omits_field():
    result = normalize_event("sessionStart", {})
    assert "source" not in result


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


# ── preToolUse (user-input tools → awaiting_elicitation) ─────────────────


def test_normalize_pre_tool_use_ask_user_promotes_to_elicitation():
    result = normalize_event("preToolUse", {"toolName": "ask_user"})
    assert result["state"] == "awaiting_elicitation"
    assert result["tool"] == "ask_user"


def test_normalize_pre_tool_use_exit_plan_mode_promotes_to_elicitation_legacy_alias():
    result = normalize_event("preToolUse", {"toolName": "exit_plan_mode"})
    assert result["state"] == "awaiting_elicitation"
    assert result["tool"] == "exit_plan_mode"


def test_normalize_pre_tool_use_regular_tool_stays_working():
    """Non-elicitation tools should keep the default 'working' state."""
    result = normalize_event("preToolUse", {"toolName": "edit"})
    assert result["state"] == "working"
    assert result["tool"] == "edit"


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


def test_normalize_post_tool_use_denied_maps_to_tool_denied():
    payload = _load_fixture("postToolUseDenied.json")
    result = normalize_event("postToolUse", payload)
    assert result["state"] == "tool_denied"
    assert result["tool"] == "bash"
    assert result["result"] == "denied"


def test_normalize_post_tool_use_failure_via_result_type():
    payload = _load_fixture("postToolUseFailure_via_postToolUse.json")
    result = normalize_event("postToolUse", payload)
    assert result["state"] == "tool_error"
    assert result["tool"] == "bash"
    assert result["result"] == "failure"


def test_normalize_post_tool_use_success_stays_tool_ok():
    """Explicit success resultType keeps the default tool_ok state."""
    payload = {
        "toolName": "edit",
        "toolResult": {"resultType": "success", "textResultForLlm": "ok"},
    }
    result = normalize_event("postToolUse", payload)
    assert result["state"] == "tool_ok"
    assert result["result"] == "success"


def test_normalize_post_tool_use_no_result_type_stays_tool_ok():
    """Missing resultType (backward compat) keeps tool_ok."""
    result = normalize_event("postToolUse", {"toolName": "edit", "toolResult": {}})
    assert result["state"] == "tool_ok"
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
    assert result["reason"] == "end_turn"
    assert result["transcript_path"] == "/tmp/subagent-x.jsonl"


def test_normalize_subagent_stop_empty_payload_omits_reason():
    result = normalize_event("subagentStop", {})
    assert result["state"] == "idle"
    assert "reason" not in result


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


# ── notification (permission_prompt) ──────────────────────────────────────


def test_normalize_permission_prompt_promotes_to_persistent_state():
    result = normalize_event(
        "notification",
        {"notification_type": "permission_prompt", "message": "Edit file: foo.py"},
    )
    assert result["event"] == "notification"
    assert result["state"] == "awaiting_permission"
    assert result["notification_type"] == "permission_prompt"
    assert result["message"] == "Edit file: foo.py"


def test_normalize_permission_prompt_carries_ttl():
    result = normalize_event(
        "notification",
        {"notification_type": "permission_prompt"},
    )
    assert result["state"] == "awaiting_permission"
    assert isinstance(result["ttl_s"], int)
    assert result["ttl_s"] == 600


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


def test_normalize_prefers_payload_session_id_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A payload sessionId takes precedence over the wrapper fallback."""
    monkeypatch.setenv("COPILOT_RING_CLI_PID", "42")
    result = normalize_event(
        "preToolUse",
        {"toolName": "edit", "sessionId": "payload-session"},
    )
    assert result["session"] == "payload-session"


def test_normalize_uses_payload_session_id_without_env() -> None:
    """A payload sessionId is enough to populate the session field."""
    result = normalize_event(
        "preToolUse",
        {"toolName": "edit", "sessionId": "payload-session"},
    )
    assert result["session"] == "payload-session"


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


def test_pre_tool_use_ask_user_carries_elicitation_ttl():
    result = normalize_event("preToolUse", {"toolName": "ask_user"})
    assert result["state"] == "awaiting_elicitation"
    assert isinstance(result["ttl_s"], int)
    assert result["ttl_s"] == 600


def test_pre_tool_use_regular_tool_carries_working_ttl():
    result = normalize_event("preToolUse", {"toolName": "edit"})
    assert result["state"] == "working"
    assert isinstance(result["ttl_s"], int)
    assert result["ttl_s"] > 0


def test_all_ttl_states_are_reachable():
    """Every persistent state with a TTL must be reachable from some event path.

    Catches orphaned states — states fully defined in firmware, priority,
    and TTL tables but never routed to by any event mapping or runtime
    promotion.  This is the class of bug where a new state is wired up
    everywhere *except* the event-to-state routing.

    Validates both camelCase and PascalCase (VS Code-compatible) event
    names so a state added under one form but not the other still gets
    caught.
    """
    from copilot_command_ring.constants import (
        ELICITATION_NOTIFICATION_TYPE,
        ELICITATION_TOOL_NAMES,
        EVENT_NAME_ALIASES,
        EVENT_STATE_MAP,
        PERMISSION_NOTIFICATION_TYPE,
        STATE_TTL_DEFAULTS,
    )

    # States reachable via direct EVENT_STATE_MAP values
    reachable: set[str] = set(EVENT_STATE_MAP.values())

    def _add_state(message: dict[str, object]) -> None:
        state = message["state"]
        assert isinstance(state, str)
        reachable.add(state)

    # States reachable via runtime promotions in normalize_event:
    #  - preToolUse with user-input tools → awaiting_elicitation
    #  - notification with elicitation_dialog → awaiting_elicitation
    #  - notification with permission_prompt → awaiting_permission
    #  - postToolUse denied/failure → tool_denied/tool_error
    for tool_name in ELICITATION_TOOL_NAMES:
        _add_state(normalize_event("preToolUse", {"toolName": tool_name}))
    _add_state(
        normalize_event(
            "notification",
            {"notification_type": ELICITATION_NOTIFICATION_TYPE},
        ),
    )
    _add_state(
        normalize_event(
            "notification",
            {"notification_type": PERMISSION_NOTIFICATION_TYPE},
        ),
    )
    for result_type, _expected_state in [("denied", "tool_denied"), ("failure", "tool_error")]:
        _add_state(
            normalize_event(
                "postToolUse",
                {"toolName": "x", "toolResult": {"resultType": result_type}},
            ),
        )

    # Walk PascalCase aliases too: every alias must resolve to a state
    # that is also in the reachable set (no orphaned PascalCase-only
    # paths).  An empty payload is sufficient since the alias resolution
    # happens before any field extraction.
    for alias in EVENT_NAME_ALIASES:
        _add_state(normalize_event(alias, {}))

    orphaned = set(STATE_TTL_DEFAULTS.keys()) - reachable
    assert not orphaned, (
        f"States with TTL defaults but no event path: {sorted(orphaned)}. "
        "Ensure EVENT_STATE_MAP or a normalize_event promotion routes to these states."
    )


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

    denied = normalize_event(
        "postToolUse",
        {"toolName": "bash", "toolResult": {"resultType": "denied"}},
    )
    assert denied["state"] == "tool_denied"
    assert "ttl_s" not in denied

    notify = normalize_event("notification", {})
    assert notify["state"] == "notify"
    assert "ttl_s" not in notify


# ── VS Code-compatible dual-format (PascalCase + snake_case) ────────────

# Map of PascalCase event name → expected canonical state, mirroring
# EVENT_NAME_ALIASES in constants.py.  Kept here as a literal so a future
# alias drift accidentally added to constants.py without a corresponding
# state mapping is caught explicitly.
_PASCALCASE_ALIASES: dict[str, str] = {
    "SessionStart": "session_start",
    "SessionEnd": "off",
    "UserPromptSubmit": "prompt_submitted",
    "PreToolUse": "working",
    "PostToolUse": "tool_ok",
    "PostToolUseFailure": "tool_error",
    "Stop": "agent_idle",  # NB: irregular — alias is "Stop", not "AgentStop"
    "SubagentStop": "idle",
    "ErrorOccurred": "error",
    "PreCompact": "compacting",
    "Notification": "notify",
}


@pytest.mark.parametrize(("alias", "expected_state"), list(_PASCALCASE_ALIASES.items()))
def test_pascalcase_event_aliases_resolve_to_canonical_state(
    alias: str,
    expected_state: str,
) -> None:
    """PascalCase event names map to the same state as their camelCase form."""
    result = normalize_event(alias, {})
    assert result["state"] == expected_state, (
        f"{alias} resolved to {result['state']!r}, expected {expected_state!r}"
    )
    # Original event name preserved on the wire for log correlation.
    assert result["event"] == alias


def test_pascalcase_stop_alias_is_not_agentstop() -> None:
    """Guard the irregular alias: the docs spell it ``Stop``, not ``AgentStop``."""
    from copilot_command_ring.constants import EVENT_NAME_ALIASES

    assert "Stop" in EVENT_NAME_ALIASES
    assert EVENT_NAME_ALIASES["Stop"] == "agentStop"
    assert "AgentStop" not in EVENT_NAME_ALIASES


def test_pascalcase_aliases_match_constants() -> None:
    """The test-local PascalCase map matches EVENT_NAME_ALIASES exactly.

    Prevents the test file and the production constants from drifting.
    """
    from copilot_command_ring.constants import EVENT_NAME_ALIASES

    assert set(_PASCALCASE_ALIASES.keys()) == set(EVENT_NAME_ALIASES.keys())


def test_unaliased_events_have_no_pascalcase_alias() -> None:
    """``subagentStart`` and ``permissionRequest`` have no documented alias."""
    from copilot_command_ring.constants import EVENT_NAME_ALIASES

    for unaliased in ("SubagentStart", "PermissionRequest"):
        assert unaliased not in EVENT_NAME_ALIASES


# ── Snake_case payload field extraction ───────────────────────────────


def test_pre_tool_use_snake_case_tool_name() -> None:
    """PreToolUse + snake_case ``tool_name`` produces same state as camelCase."""
    cc = normalize_event("preToolUse", {"toolName": "edit"})
    sc = normalize_event("PreToolUse", {"tool_name": "edit"})
    assert sc["state"] == cc["state"] == "working"
    assert sc["tool"] == cc["tool"] == "edit"


def test_pre_tool_use_snake_case_ask_user_promotes() -> None:
    """snake_case ``tool_name: "ask_user"`` still promotes to awaiting_elicitation."""
    result = normalize_event("PreToolUse", {"tool_name": "ask_user"})
    assert result["state"] == "awaiting_elicitation"
    assert result["tool"] == "ask_user"


def test_post_tool_use_snake_case_result_type() -> None:
    """PostToolUse + snake_case ``tool_result.result_type`` overrides state."""
    result = normalize_event(
        "PostToolUse",
        {
            "tool_name": "bash",
            "tool_result": {"result_type": "failure"},
        },
    )
    assert result["state"] == "tool_error"
    assert result["tool"] == "bash"
    assert result["result"] == "failure"


def test_post_tool_use_snake_case_denied() -> None:
    result = normalize_event(
        "PostToolUse",
        {"tool_name": "edit", "tool_result": {"result_type": "denied"}},
    )
    assert result["state"] == "tool_denied"
    assert result["result"] == "denied"


def test_post_tool_use_failure_snake_case() -> None:
    result = normalize_event(
        "PostToolUseFailure",
        {"tool_name": "bash", "error": "Command failed"},
    )
    assert result["state"] == "tool_error"
    assert result["tool"] == "bash"
    assert result["error"] == "Command failed"


def test_subagent_stop_snake_case() -> None:
    result = normalize_event(
        "SubagentStop",
        {
            "agent_name": "reviewer",
            "agent_display_name": "Code Reviewer",
            "transcript_path": "/tmp/x.jsonl",
        },
    )
    assert result["state"] == "idle"
    assert result["agent"] == "reviewer"
    assert result["agent_display_name"] == "Code Reviewer"
    assert result["transcript_path"] == "/tmp/x.jsonl"


def test_agent_stop_snake_case_stop_reason() -> None:
    result = normalize_event(
        "Stop",
        {"stop_reason": "end_turn", "transcript_path": "/tmp/x.jsonl"},
    )
    assert result["state"] == "agent_idle"
    assert result["reason"] == "end_turn"
    assert result["transcript_path"] == "/tmp/x.jsonl"


def test_subagent_stop_snake_case_stop_reason() -> None:
    result = normalize_event(
        "SubagentStop",
        {
            "agent_name": "reviewer",
            "stop_reason": "end_turn",
            "transcript_path": "/tmp/sub.jsonl",
        },
    )
    assert result["state"] == "idle"
    assert result["agent"] == "reviewer"
    assert result["reason"] == "end_turn"
    assert result["transcript_path"] == "/tmp/sub.jsonl"


def test_subagent_stop_camel_case_stop_reason() -> None:
    result = normalize_event(
        "subagentStop",
        {"agentName": "reviewer", "stopReason": "end_turn"},
    )
    assert result["state"] == "idle"
    assert result["agent"] == "reviewer"
    assert result["reason"] == "end_turn"


def test_error_occurred_snake_case_error_context() -> None:
    result = normalize_event(
        "ErrorOccurred",
        {
            "error": {"name": "ToolFailure", "message": "timeout"},
            "recoverable": True,
            "error_context": "tool_execution",
        },
    )
    assert result["state"] == "error"
    assert result["error"] == "ToolFailure"
    assert result["message"] == "timeout"
    assert result["recoverable"] is True
    assert result["errorContext"] == "tool_execution"


def test_pre_compact_snake_case() -> None:
    result = normalize_event(
        "PreCompact",
        {
            "trigger": "auto",
            "transcript_path": "/tmp/x.jsonl",
            "custom_instructions": "preserve tests",
        },
    )
    assert result["state"] == "compacting"
    assert result["trigger"] == "auto"
    assert result["transcript_path"] == "/tmp/x.jsonl"
    assert result["custom_instructions"] == "preserve tests"


def test_session_start_snake_case_initial_prompt() -> None:
    result = normalize_event(
        "SessionStart",
        {"source": "resume", "initial_prompt": "continue last task"},
    )
    assert result["state"] == "session_start"
    assert result["source"] == "resume"
    assert result["initial_prompt"] == "continue last task"


def test_session_id_snake_case_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    """snake_case ``session_id`` is preferred over the ENV_CLI_PID fallback."""
    from copilot_command_ring.constants import ENV_CLI_PID

    monkeypatch.setenv(ENV_CLI_PID, "12345")
    result = normalize_event("SessionStart", {"session_id": "abc-def-ghi"})
    assert result["session"] == "abc-def-ghi"


def test_session_id_camel_case_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """camelCase ``sessionId`` continues to win over ENV_CLI_PID."""
    from copilot_command_ring.constants import ENV_CLI_PID

    monkeypatch.setenv(ENV_CLI_PID, "12345")
    result = normalize_event("sessionStart", {"sessionId": "abc-def-ghi"})
    assert result["session"] == "abc-def-ghi"


def test_session_id_falls_back_to_env_when_payload_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from copilot_command_ring.constants import ENV_CLI_PID

    monkeypatch.setenv(ENV_CLI_PID, "wrapper-pid-42")
    result = normalize_event("sessionStart", {})
    assert result["session"] == "wrapper-pid-42"


def test_notification_snake_case_payload_works() -> None:
    """notification_type is snake_case in both formats — verify it still routes."""
    result = normalize_event(
        "Notification",
        {
            "notification_type": "elicitation_dialog",
            "message": "Choose an option",
            "title": "Pick one",
        },
    )
    assert result["state"] == "awaiting_elicitation"
    assert result["notification_type"] == "elicitation_dialog"
    assert result["message"] == "Choose an option"
    assert result["title"] == "Pick one"


# ── Field truncation (size cap) ───────────────────────────────────────


def test_long_tool_input_is_truncated() -> None:
    from copilot_command_ring.constants import MAX_EXTRACTED_FIELD_CHARS

    long_input = "x" * (MAX_EXTRACTED_FIELD_CHARS * 2)
    result = normalize_event("preToolUse", {"toolName": "edit", "toolArgs": long_input})
    assert "tool_input" in result
    tool_input = result["tool_input"]
    assert isinstance(tool_input, str)
    assert len(tool_input) == MAX_EXTRACTED_FIELD_CHARS + 1  # "…" suffix
    assert tool_input.endswith("…")


def test_short_tool_input_is_not_truncated() -> None:
    result = normalize_event("preToolUse", {"toolName": "edit", "toolArgs": "small"})
    assert result["tool_input"] == "small"


def test_dict_tool_input_is_stringified() -> None:
    """Non-string ``tool_input`` is stringified so JSON serialization stays safe."""
    result = normalize_event(
        "preToolUse",
        {"toolName": "edit", "toolArgs": {"path": "foo.py", "content": "..."}},
    )
    tool_input = result["tool_input"]
    assert isinstance(tool_input, str)
    assert "path" in tool_input


def test_long_error_stack_is_truncated() -> None:
    from copilot_command_ring.constants import MAX_EXTRACTED_FIELD_CHARS

    long_stack = "Traceback" + "x" * (MAX_EXTRACTED_FIELD_CHARS * 3)
    result = normalize_event(
        "errorOccurred",
        {
            "error": {"name": "Boom", "message": "m", "stack": long_stack},
        },
    )
    assert "error_stack" in result
    error_stack = result["error_stack"]
    assert isinstance(error_stack, str)
    assert len(error_stack) == MAX_EXTRACTED_FIELD_CHARS + 1
    assert error_stack.endswith("…")


def test_long_custom_instructions_is_truncated() -> None:
    from copilot_command_ring.constants import MAX_EXTRACTED_FIELD_CHARS

    long_instructions = "y" * (MAX_EXTRACTED_FIELD_CHARS * 2)
    result = normalize_event(
        "preCompact",
        {"trigger": "manual", "customInstructions": long_instructions},
    )
    custom_instructions = result["custom_instructions"]
    assert isinstance(custom_instructions, str)
    assert len(custom_instructions) == MAX_EXTRACTED_FIELD_CHARS + 1
    assert custom_instructions.endswith("…")


def test_text_result_for_llm_is_intentionally_skipped() -> None:
    """The verbatim LLM-bound tool output is intentionally NOT extracted.

    It can be many KB and may contain code or secrets — embedding it
    on the wire would strain the firmware serial buffer.
    """
    huge = "x" * 50_000
    result = normalize_event(
        "postToolUse",
        {
            "toolName": "view",
            "toolResult": {
                "resultType": "success",
                "textResultForLlm": huge,
            },
        },
    )
    # Result type still propagates, but the text payload does not.
    assert result["result"] == "success"
    assert "textResultForLlm" not in result
    assert "text_result_for_llm" not in result
    # Also verify the snake_case variant is skipped.
    result_sc = normalize_event(
        "PostToolUse",
        {
            "tool_name": "view",
            "tool_result": {
                "result_type": "success",
                "text_result_for_llm": huge,
            },
        },
    )
    assert "text_result_for_llm" not in result_sc
    assert "textResultForLlm" not in result_sc


# ── Equivalence between camelCase and PascalCase forms ────────────────


_EQUIVALENCE_CASES: list[tuple[str, dict, str, dict]] = [
    (
        "sessionStart",
        {"source": "new", "initialPrompt": "go"},
        "SessionStart",
        {"source": "new", "initial_prompt": "go"},
    ),
    (
        "preToolUse",
        {"toolName": "edit", "toolArgs": "x"},
        "PreToolUse",
        {"tool_name": "edit", "tool_input": "x"},
    ),
    (
        "postToolUse",
        {"toolName": "bash", "toolResult": {"resultType": "denied"}},
        "PostToolUse",
        {"tool_name": "bash", "tool_result": {"result_type": "denied"}},
    ),
    (
        "postToolUseFailure",
        {"toolName": "bash", "error": "boom"},
        "PostToolUseFailure",
        {"tool_name": "bash", "error": "boom"},
    ),
    (
        "agentStop",
        {"stopReason": "end_turn"},
        "Stop",
        {"stop_reason": "end_turn"},
    ),
    (
        "subagentStop",
        {"agentName": "r", "agentDisplayName": "R", "stopReason": "end_turn"},
        "SubagentStop",
        {"agent_name": "r", "agent_display_name": "R", "stop_reason": "end_turn"},
    ),
    (
        "errorOccurred",
        {"error": {"name": "E", "message": "m"}, "errorContext": "system"},
        "ErrorOccurred",
        {"error": {"name": "E", "message": "m"}, "error_context": "system"},
    ),
    (
        "preCompact",
        {"trigger": "auto", "customInstructions": "keep tests"},
        "PreCompact",
        {"trigger": "auto", "custom_instructions": "keep tests"},
    ),
]


@pytest.mark.parametrize(
    ("camel_event", "camel_payload", "pascal_event", "pascal_payload"),
    _EQUIVALENCE_CASES,
)
def test_camel_and_pascal_forms_produce_equivalent_output(
    camel_event: str,
    camel_payload: dict,
    pascal_event: str,
    pascal_payload: dict,
) -> None:
    """Both formats produce the same state + extracted fields.

    The ``event`` field always reflects the original invocation name, so
    we strip it before comparing.
    """
    cc = normalize_event(camel_event, camel_payload)
    sc = normalize_event(pascal_event, pascal_payload)
    cc.pop("event", None)
    sc.pop("event", None)
    assert cc == sc, f"Mismatch between {camel_event} and {pascal_event}"


@pytest.mark.parametrize("alias", list(_PASCALCASE_ALIASES.keys()))
def test_pascalcase_alias_empty_payload_does_not_crash(alias: str) -> None:
    result = normalize_event(alias, {})
    assert isinstance(result, dict)
    assert result["event"] == alias


# ── Fixture-driven dual-format round-trip ──────────────────────────────


_VSCODE_FIXTURES: list[tuple[str, str, str]] = [
    ("SessionStart", "SessionStart.vscode.json", "session_start"),
    ("PreToolUse", "PreToolUse.vscode.json", "working"),
    ("PostToolUse", "PostToolUse.vscode.json", "tool_ok"),
    ("PostToolUseFailure", "PostToolUseFailure.vscode.json", "tool_error"),
    ("Stop", "Stop.vscode.json", "agent_idle"),
    ("SubagentStop", "SubagentStop.vscode.json", "idle"),
    ("ErrorOccurred", "ErrorOccurred.vscode.json", "error"),
    ("PreCompact", "PreCompact.vscode.json", "compacting"),
    ("Notification", "Notification.vscode.json", "awaiting_elicitation"),
]


@pytest.mark.parametrize(("alias", "fixture", "expected_state"), _VSCODE_FIXTURES)
def test_vscode_compatible_fixture_normalizes_correctly(
    alias: str, fixture: str, expected_state: str,
) -> None:
    """End-to-end: VS Code-compatible PascalCase payload → expected state.

    Uses fixture files that match the schema documented at
    docs.github.com/en/copilot/reference/hooks-reference (PascalCase event
    name, snake_case fields, ``hook_event_name`` present).
    """
    payload = _load_fixture(fixture)
    result = normalize_event(alias, payload)
    assert result["state"] == expected_state
    assert result["event"] == alias
    # session_id from the fixture is preferred over env-derived fallback.
    assert result.get("session") == payload["session_id"]
