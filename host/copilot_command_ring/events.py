# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Event normalization for Copilot CLI hook payloads."""

from __future__ import annotations

import os

from .constants import (
    ELICITATION_NOTIFICATION_TYPE,
    ELICITATION_TOOL_NAMES,
    ENV_CLI_PID,
    EVENT_STATE_MAP,
    STATE_AWAITING_ELICITATION,
    STATE_IDLE,
    STATE_TOOL_DENIED,
    STATE_TOOL_ERROR,
    STATE_TTL_DEFAULTS,
)


def _set_if(out: dict[str, object], key: str, value: object) -> None:
    """Add *key* to *out* only when *value* is not ``None``."""
    if value is not None:
        out[key] = value


def normalize_event(
    event_name: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Turn a raw Copilot CLI hook event into a normalized dict.

    Unknown event names produce a valid message with ``state="idle"``.
    Missing payload fields are silently omitted — the function never raises
    on absent keys.
    """
    out: dict[str, object] = {
        "event": event_name,
        "state": EVENT_STATE_MAP.get(event_name, STATE_IDLE),
    }

    if event_name == "sessionEnd":
        _set_if(out, "reason", payload.get("reason"))

    elif event_name == "sessionStart":
        _set_if(out, "source", payload.get("source"))

    elif event_name == "preToolUse":
        tool_name = payload.get("toolName")
        _set_if(out, "tool", tool_name)
        # Tools that block on user input promote to awaiting_elicitation
        # so the ring shows a yellow pulse instead of the working spinner.
        if isinstance(tool_name, str) and tool_name in ELICITATION_TOOL_NAMES:
            out["state"] = STATE_AWAITING_ELICITATION

    elif event_name == "postToolUse":
        _set_if(out, "tool", payload.get("toolName"))
        result_obj = payload.get("toolResult")
        if isinstance(result_obj, dict):
            result_type = result_obj.get("resultType")
            _set_if(out, "result", result_type)
            # Override state based on resultType so the ring doesn't show
            # green for denied or failed tool executions.
            if result_type == "denied":
                out["state"] = STATE_TOOL_DENIED
            elif result_type == "failure":
                out["state"] = STATE_TOOL_ERROR

    elif event_name == "postToolUseFailure":
        _set_if(out, "tool", payload.get("toolName"))
        _set_if(out, "error", payload.get("error"))

    elif event_name == "permissionRequest":
        _set_if(out, "tool", payload.get("toolName"))

    elif event_name in ("subagentStart", "subagentStop"):
        _set_if(out, "agent", payload.get("agentName"))

    elif event_name == "agentStop":
        _set_if(out, "reason", payload.get("stopReason"))

    elif event_name == "preCompact":
        _set_if(out, "trigger", payload.get("trigger"))

    elif event_name == "errorOccurred":
        error_obj = payload.get("error")
        if isinstance(error_obj, dict):
            _set_if(out, "error", error_obj.get("name"))
            _set_if(out, "message", error_obj.get("message"))
        _set_if(out, "recoverable", payload.get("recoverable"))
        _set_if(out, "errorContext", payload.get("errorContext"))

    elif event_name == "notification":
        _set_if(out, "notification_type", payload.get("notification_type"))
        _set_if(out, "message", payload.get("message"))
        # Elicitation dialogs promote to a persistent state — the agent is
        # blocked waiting for user input and the ring should stay lit.
        if payload.get("notification_type") == ELICITATION_NOTIFICATION_TYPE:
            out["state"] = STATE_AWAITING_ELICITATION

    # Session ID for multi-session firmware arbitration
    _set_if(out, "session", os.environ.get(ENV_CLI_PID))

    # Optional TTL so the firmware can decay stuck persistent states to
    # agent_idle if no refresh arrives within the window. Transient states
    # and states without a default (e.g. agent_idle) omit the field.
    ttl_s = STATE_TTL_DEFAULTS.get(out["state"])  # type: ignore[arg-type]
    if ttl_s is not None:
        out["ttl_s"] = ttl_s

    return out
