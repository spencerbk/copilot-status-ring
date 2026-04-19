# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Event normalization for Copilot CLI hook payloads."""

from __future__ import annotations

from .constants import EVENT_STATE_MAP, STATE_IDLE


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

    elif event_name == "preToolUse":
        _set_if(out, "tool", payload.get("toolName"))

    elif event_name == "postToolUse":
        _set_if(out, "tool", payload.get("toolName"))
        result_obj = payload.get("toolResult")
        if isinstance(result_obj, dict):
            _set_if(out, "result", result_obj.get("resultType"))

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

    return out
