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
STATE_AWAITING_PERMISSION: Final[str] = "awaiting_permission"
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
    "permissionRequest": STATE_WORKING,
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
DEFAULT_IDLE_MODE: Final[str] = "off"
DEFAULT_PIXEL_COUNT: Final[int] = 24

# ---------------------------------------------------------------------------
# Environment variable names
# ---------------------------------------------------------------------------
ENV_PORT: Final[str] = "COPILOT_RING_PORT"
ENV_BAUD: Final[str] = "COPILOT_RING_BAUD"
ENV_BRIGHTNESS: Final[str] = "COPILOT_RING_BRIGHTNESS"
ENV_LOG_LEVEL: Final[str] = "COPILOT_RING_LOG_LEVEL"
ENV_DRY_RUN: Final[str] = "COPILOT_RING_DRY_RUN"
ENV_LOCK_TIMEOUT: Final[str] = "COPILOT_RING_LOCK_TIMEOUT"

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
    "Arduino",
    "USB Serial",
    "Seeed",
]
