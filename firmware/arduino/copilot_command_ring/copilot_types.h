// SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
// SPDX-License-Identifier: MIT
//
// Shared type definitions for the Copilot Command Ring Arduino firmware.
// Separated into a header so the Arduino preprocessor sees these types
// before it auto-generates function prototypes.

#ifndef COPILOT_TYPES_H
#define COPILOT_TYPES_H

#include <stdint.h>

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

#define NEOPIXEL_PIN      6
#define PIXEL_COUNT       24
#define BRIGHTNESS        10        // 0-255, ~4%
#define BRIGHTNESS_BOOST  5         // extra for dim states (agent_idle breathing)
#define SERIAL_BAUD       115200
#define SERIAL_BUF_SIZE   256
#define MAX_SESSIONS      8
#define STALE_TIMEOUT_MS  300000UL  // 300 s — prune sessions with no messages
#define SERIAL_SILENCE_MS 600000UL  // 600 s — reset when active sessions + no serial
#define WATCHDOG_MS       8000      // 8 s hardware watchdog
#define MAX_CONSEC_ERRORS 10        // force reset after consecutive parse failures
#define LOOP_DELAY_MS     20        // ~50 fps
#define SESSION_ID_LEN    32

// ---------------------------------------------------------------------------
// State enum
// ---------------------------------------------------------------------------

enum State : uint8_t {
  ST_OFF,
  ST_SESSION_START,
  ST_PROMPT_SUBMITTED,
  ST_WORKING,
  ST_TOOL_OK,
  ST_TOOL_ERROR,
  ST_TOOL_DENIED,
  ST_AWAITING_PERMISSION,
  ST_AWAITING_ELICITATION,
  ST_SUBAGENT_ACTIVE,
  ST_AGENT_IDLE,
  ST_COMPACTING,
  ST_ERROR,
  ST_NOTIFY,
  ST_IDLE,
  ST_COUNT  // sentinel — must be last
};

// ---------------------------------------------------------------------------
// Idle mode
// ---------------------------------------------------------------------------

enum IdleMode : uint8_t {
  IDLE_BREATHING,  // default — breathe when no sessions remain
  IDLE_OFF,        // go dark when no sessions remain
  IDLE_UNSET       // not specified in message
};

// ---------------------------------------------------------------------------
// Parsed message struct
// ---------------------------------------------------------------------------

struct ParsedMessage {
  State    state;
  char     session[SESSION_ID_LEN];  // empty string = no session
  uint32_t ttlMs;
  bool     hasTtl;
  IdleMode idleMode;
  bool     valid;
};

// ---------------------------------------------------------------------------
// Session tracker entry
// ---------------------------------------------------------------------------

struct SessionEntry {
  char     id[SESSION_ID_LEN];
  State    persistent;
  uint32_t lastSeenMs;
  uint32_t ttlMs;
  bool     hasTtl;
  bool     occupied;
};

// ---------------------------------------------------------------------------
// Resolve result
// ---------------------------------------------------------------------------

struct ResolveResult {
  State winning;
  State transient;
  bool  hasTransient;
};

#endif // COPILOT_TYPES_H
