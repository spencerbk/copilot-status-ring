# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Constants for the Copilot Command Ring host bridge."""

from typing import Final

# ---------------------------------------------------------------------------
# Normalized state names
# ---------------------------------------------------------------------------
STATE_SESSION_START: Final[str] = "session_start"
STATE_PROMPT_SUBMITTED: Final[str] = "prompt_submitted"
STATE_WORKING: Final[str] = "working"
STATE_TOOL_OK: Final[str] = "tool_ok"
STATE_TOOL_ERROR: Final[str] = "tool_error"
STATE_TOOL_DENIED: Final[str] = "tool_denied"
STATE_AWAITING_PERMISSION: Final[str] = "awaiting_permission"
STATE_AWAITING_ELICITATION: Final[str] = "awaiting_elicitation"
STATE_SUBAGENT_ACTIVE: Final[str] = "subagent_active"
STATE_AGENT_IDLE: Final[str] = "agent_idle"
STATE_COMPACTING: Final[str] = "compacting"
STATE_ERROR: Final[str] = "error"
STATE_OFF: Final[str] = "off"
STATE_NOTIFY: Final[str] = "notify"
STATE_IDLE: Final[str] = "idle"

# ---------------------------------------------------------------------------
# Event-to-state mapping (Copilot CLI hook event → normalized state)
# ---------------------------------------------------------------------------
EVENT_STATE_MAP: Final[dict[str, str]] = {
    "sessionStart": STATE_SESSION_START,
    "sessionEnd": STATE_OFF,
    "userPromptSubmitted": STATE_PROMPT_SUBMITTED,
    "preToolUse": STATE_WORKING,
    "postToolUse": STATE_TOOL_OK,
    "postToolUseFailure": STATE_TOOL_ERROR,
    "permissionRequest": STATE_AWAITING_PERMISSION,
    "subagentStart": STATE_SUBAGENT_ACTIVE,
    "subagentStop": STATE_IDLE,
    "agentStop": STATE_AGENT_IDLE,
    "preCompact": STATE_COMPACTING,
    "errorOccurred": STATE_ERROR,
    "notification": STATE_NOTIFY,
}

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------
DEFAULT_BAUD: Final[int] = 115200
DEFAULT_BRIGHTNESS: Final[float] = 0.04
DEFAULT_SERIAL_OPEN_TIMEOUT: Final[float] = 0.3
DEFAULT_SERIAL_WRITE_TIMEOUT: Final[float] = 0.3
DEFAULT_LOCK_TIMEOUT: Final[float] = 1.0
DEFAULT_IDLE_MODE: Final[str] = "breathing"
DEFAULT_PIXEL_COUNT: Final[int] = 24

# ---------------------------------------------------------------------------
# Idle-mode values (carried in each outgoing message so the firmware can
# honor the user's preference for what the ring does when a session ends).
# ---------------------------------------------------------------------------
IDLE_MODE_BREATHING: Final[str] = "breathing"
IDLE_MODE_OFF: Final[str] = "off"
VALID_IDLE_MODES: Final[frozenset[str]] = frozenset(
    {IDLE_MODE_BREATHING, IDLE_MODE_OFF},
)

# ---------------------------------------------------------------------------
# Per-state TTL defaults (seconds). The firmware decays any persistent state
# to ``agent_idle`` if not refreshed within its TTL. States not listed here
# are sent without a ``ttl_s`` field — the firmware treats them as having
# no decay. Transient states never get a TTL.
# ---------------------------------------------------------------------------
STATE_TTL_DEFAULTS: Final[dict[str, int]] = {
    "session_start": 60,
    "prompt_submitted": 120,
    "working": 300,
    "awaiting_permission": 600,
    "awaiting_elicitation": 600,
    "subagent_active": 300,
    "compacting": 300,
    "error": 60,
}

# ---------------------------------------------------------------------------
# Host-side failure surfacing
# ---------------------------------------------------------------------------
CONSECUTIVE_FAILURE_THRESHOLD: Final[int] = 3
FAILURE_COUNTER_FILENAME: Final[str] = "copilot-command-ring.failcount"

# ---------------------------------------------------------------------------
# Environment variable names
# ---------------------------------------------------------------------------
ENV_PORT: Final[str] = "COPILOT_RING_PORT"
ENV_BAUD: Final[str] = "COPILOT_RING_BAUD"
ENV_BRIGHTNESS: Final[str] = "COPILOT_RING_BRIGHTNESS"
ENV_LOG_LEVEL: Final[str] = "COPILOT_RING_LOG_LEVEL"
ENV_DRY_RUN: Final[str] = "COPILOT_RING_DRY_RUN"
ENV_LOCK_TIMEOUT: Final[str] = "COPILOT_RING_LOCK_TIMEOUT"
ENV_CLI_PID: Final[str] = "COPILOT_RING_CLI_PID"

# ---------------------------------------------------------------------------
# Config file name
# ---------------------------------------------------------------------------
CONFIG_FILE_NAME: Final[str] = ".copilot-command-ring.local.json"

# ---------------------------------------------------------------------------
# Device detection defaults
# ---------------------------------------------------------------------------
DEFAULT_DESCRIPTION_CONTAINS: Final[list[str]] = [
    "Copilot Command Ring",
    "CircuitPython",
    "MicroPython",
    "Arduino",
    "USB Serial",
    "Seeed",
]

# ---------------------------------------------------------------------------
# Notification types that promote to a persistent state
# ---------------------------------------------------------------------------
ELICITATION_NOTIFICATION_TYPE: Final[str] = "elicitation_dialog"

# ---------------------------------------------------------------------------
# Tool names that block on user input. ``ask_user`` is current; keep the
# older ``exit_plan_mode`` alias for compatibility with prior runtimes.
# When preToolUse fires for one of these, the host promotes the state to
# awaiting_elicitation so the ring shows a yellow pulse instead of a
# purple working spinner.
# ---------------------------------------------------------------------------
ELICITATION_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {"ask_user", "exit_plan_mode"},
)
