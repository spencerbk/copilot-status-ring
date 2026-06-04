# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Event normalization for Copilot CLI hook payloads.

Handles both Copilot CLI naming conventions documented at
docs.github.com/en/copilot/reference/hooks-reference:

* camelCase event names + camelCase payload fields (our deploy format)
* PascalCase event names + snake_case payload fields (VS Code-compatible;
  used by cross-tool ``.claude/settings.json`` files the runtime reads)

Both forms resolve to the same normalized state and field set on the wire.
The original event name the runtime invoked us with is preserved in the
``event`` field for log correlation.
"""

from __future__ import annotations

import os

from .constants import (
    ELICITATION_NOTIFICATION_TYPE,
    ELICITATION_TOOL_NAMES,
    ENV_CLI_PID,
    EVENT_NAME_ALIASES,
    EVENT_STATE_MAP,
    MAX_EXTRACTED_FIELD_CHARS,
    PERMISSION_NOTIFICATION_TYPE,
    STATE_AWAITING_ELICITATION,
    STATE_AWAITING_PERMISSION,
    STATE_IDLE,
    STATE_TOOL_DENIED,
    STATE_TOOL_ERROR,
    STATE_TTL_DEFAULTS,
)


def _set_if(out: dict[str, object], key: str, value: object) -> None:
    """Add *key* to *out* only when *value* is not ``None``."""
    if value is not None:
        out[key] = value


def _pick(payload: dict[str, object], *keys: str) -> object | None:
    """Return the first non-``None`` value among *keys* in *payload*.

    Used to read documented payload fields in a format-agnostic way: the
    camelCase variant is tried first (matches our own deploy), with the
    snake_case fallback honoring VS Code-compatible PascalCase invocations.
    """
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _truncate(value: object, limit: int = MAX_EXTRACTED_FIELD_CHARS) -> str | None:
    """Stringify *value* and truncate to *limit* chars with an ellipsis suffix.

    Returns ``None`` when *value* is ``None`` so the caller can use
    :func:`_set_if` to omit absent fields.  Truncation keeps the serial
    wire small for fields that can grow unbounded (tool args, stack
    traces, custom compaction instructions).
    """
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _session_value(payload: dict[str, object]) -> str | None:
    """Return the best available session identifier for multi-session tracking.

    Honors both ``sessionId`` (camelCase) and ``session_id`` (snake_case /
    VS Code-compatible) so PascalCase invocations keep the stable Copilot
    session id instead of falling back to ``ENV_CLI_PID``.
    """
    payload_session = _pick(payload, "sessionId", "session_id")
    if isinstance(payload_session, str) and payload_session:
        return payload_session

    env_session = os.environ.get(ENV_CLI_PID)
    return env_session or None


def normalize_event(
    event_name: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Turn a raw Copilot CLI hook event into a normalized dict.

    *event_name* may be either the camelCase form (e.g. ``preToolUse``) or
    the VS Code-compatible PascalCase form (e.g. ``PreToolUse``).  The
    output's ``event`` field preserves the original *event_name* the
    runtime invoked us with; the ``state`` is resolved through
    :data:`EVENT_NAME_ALIASES` so both forms map to the same state.

    Unknown event names produce a valid message with ``state="idle"``.
    Missing payload fields are silently omitted — the function never raises
    on absent keys.
    """
    # Resolve PascalCase aliases (e.g. ``Stop`` → ``agentStop``) before
    # the state lookup. Preserve the original name in the wire ``event``
    # field so downstream log consumers can still see how we were called.
    canonical_event = EVENT_NAME_ALIASES.get(event_name, event_name)

    out: dict[str, object] = {
        "event": event_name,
        "state": EVENT_STATE_MAP.get(canonical_event, STATE_IDLE),
    }

    # Common infra fields documented on every event (sessionId/session_id is
    # handled separately at the bottom for ENV_CLI_PID fallback semantics).
    _set_if(out, "timestamp", _pick(payload, "timestamp"))
    _set_if(out, "cwd", _pick(payload, "cwd"))

    if canonical_event == "sessionEnd":
        _set_if(out, "reason", _pick(payload, "reason"))

    elif canonical_event == "sessionStart":
        _set_if(out, "source", _pick(payload, "source"))
        _set_if(
            out,
            "initial_prompt",
            _truncate(_pick(payload, "initialPrompt", "initial_prompt")),
        )

    elif canonical_event == "userPromptSubmitted":
        # ``prompt`` may contain free-form user text; cap it like other
        # unbounded fields to keep the wire small.
        _set_if(out, "prompt", _truncate(_pick(payload, "prompt")))

    elif canonical_event == "preToolUse":
        tool_name = _pick(payload, "toolName", "tool_name")
        _set_if(out, "tool", tool_name)
        _set_if(
            out,
            "tool_input",
            _truncate(_pick(payload, "toolArgs", "tool_input")),
        )
        # Tools that block on user input promote to awaiting_elicitation
        # so the ring shows a yellow pulse instead of the working spinner.
        if isinstance(tool_name, str) and tool_name in ELICITATION_TOOL_NAMES:
            out["state"] = STATE_AWAITING_ELICITATION

    elif canonical_event == "postToolUse":
        _set_if(out, "tool", _pick(payload, "toolName", "tool_name"))
        _set_if(
            out,
            "tool_input",
            _truncate(_pick(payload, "toolArgs", "tool_input")),
        )
        result_obj = _pick(payload, "toolResult", "tool_result")
        if isinstance(result_obj, dict):
            result_type = _pick(result_obj, "resultType", "result_type")
            _set_if(out, "result", result_type)
            # text_result_for_llm / textResultForLlm is the verbatim
            # LLM-bound tool output (can be many KB for view/grep/bash
            # and may contain code or secrets).  Intentionally NOT
            # extracted — a 24-LED ring doesn't need it, and embedding
            # it in every wire message would strain the serial buffer
            # and leak content to the firmware log.
            # Override state based on resultType so the ring doesn't show
            # green for denied or failed tool executions.
            if result_type == "denied":
                out["state"] = STATE_TOOL_DENIED
            elif result_type == "failure":
                out["state"] = STATE_TOOL_ERROR

    elif canonical_event == "postToolUseFailure":
        _set_if(out, "tool", _pick(payload, "toolName", "tool_name"))
        _set_if(
            out,
            "tool_input",
            _truncate(_pick(payload, "toolArgs", "tool_input")),
        )
        _set_if(out, "error", _truncate(_pick(payload, "error")))

    elif canonical_event == "permissionRequest":
        _set_if(out, "tool", _pick(payload, "toolName", "tool_name"))

    elif canonical_event == "subagentStart":
        _set_if(out, "agent", _pick(payload, "agentName", "agent_name"))
        _set_if(
            out,
            "agent_display_name",
            _pick(payload, "agentDisplayName", "agent_display_name"),
        )
        _set_if(
            out,
            "agent_description",
            _truncate(_pick(payload, "agentDescription", "agent_description")),
        )
        _set_if(
            out,
            "transcript_path",
            _pick(payload, "transcriptPath", "transcript_path"),
        )

    elif canonical_event == "subagentStop":
        _set_if(out, "agent", _pick(payload, "agentName", "agent_name"))
        _set_if(
            out,
            "agent_display_name",
            _pick(payload, "agentDisplayName", "agent_display_name"),
        )
        _set_if(out, "reason", _pick(payload, "stopReason", "stop_reason"))
        _set_if(
            out,
            "transcript_path",
            _pick(payload, "transcriptPath", "transcript_path"),
        )

    elif canonical_event == "agentStop":
        _set_if(out, "reason", _pick(payload, "stopReason", "stop_reason"))
        _set_if(
            out,
            "transcript_path",
            _pick(payload, "transcriptPath", "transcript_path"),
        )

    elif canonical_event == "preCompact":
        _set_if(out, "trigger", _pick(payload, "trigger"))
        _set_if(
            out,
            "transcript_path",
            _pick(payload, "transcriptPath", "transcript_path"),
        )
        _set_if(
            out,
            "custom_instructions",
            _truncate(_pick(payload, "customInstructions", "custom_instructions")),
        )

    elif canonical_event == "errorOccurred":
        error_obj = _pick(payload, "error")
        if isinstance(error_obj, dict):
            _set_if(out, "error", _pick(error_obj, "name"))
            _set_if(out, "message", _truncate(_pick(error_obj, "message")))
            _set_if(out, "error_stack", _truncate(_pick(error_obj, "stack")))
        _set_if(out, "recoverable", _pick(payload, "recoverable"))
        _set_if(
            out,
            "errorContext",
            _pick(payload, "errorContext", "error_context"),
        )

    elif canonical_event == "notification":
        # ``notification_type`` is snake_case in BOTH the camelCase and
        # PascalCase forms per the hooks reference; no fallback needed.
        notification_type = payload.get("notification_type")
        _set_if(out, "notification_type", notification_type)
        _set_if(out, "title", _pick(payload, "title"))
        _set_if(out, "message", _truncate(_pick(payload, "message")))
        # Elicitation dialogs promote to a persistent state — the agent is
        # blocked waiting for user input and the ring should stay lit.
        if notification_type == ELICITATION_NOTIFICATION_TYPE:
            out["state"] = STATE_AWAITING_ELICITATION
        # Permission prompts promote similarly — the user is blocked on an
        # interactive approval dialog. This only fires in non-yolo mode;
        # auto-approved permissions never emit a permission_prompt notification.
        elif notification_type == PERMISSION_NOTIFICATION_TYPE:
            out["state"] = STATE_AWAITING_PERMISSION

    # Session ID for multi-session firmware arbitration. Prefer the stable
    # Copilot sessionId from the hook payload (either case); fall back to
    # the wrapper's process-derived ID for older runtimes or empty payloads.
    _set_if(out, "session", _session_value(payload))

    # Optional TTL so the firmware can decay stuck persistent states to
    # agent_idle if no refresh arrives within the window. Transient states
    # and states without a default (e.g. agent_idle) omit the field.
    ttl_s = STATE_TTL_DEFAULTS.get(out["state"])  # type: ignore[arg-type]
    if ttl_s is not None:
        out["ttl_s"] = ttl_s

    return out
