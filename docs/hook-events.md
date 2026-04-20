# Hook Events Reference

This document describes every Copilot CLI hook event that the Copilot Command Ring handles, the serial protocol, and the normalized messages sent to the firmware.

---

## Protocol overview

The host bridge sends **JSON Lines** to the microcontroller over USB serial:

- **Encoding:** UTF-8
- **Format:** One JSON object per line, terminated by `\n`
- **Baud:** 115200 (Arduino default; CircuitPython uses `usb_cdc.data` which is speed-independent)
- **Direction:** Host → MCU (one-way in v1)

The firmware must:

- Ignore unknown JSON keys
- Fall back to a safe default for unknown `state` values
- Discard malformed lines without crashing

---

## Event mapping table

Every message includes at minimum an `event` (the original Copilot hook event name) and a `state` (the normalized semantic state for the firmware).

| Event | State | Animation | Color | Extracted fields |
|-------|-------|-----------|-------|------------------|
| `sessionStart` | `session_start` | Soft white wipe | White | — |
| `userPromptSubmitted` | `prompt_submitted` | Wipe | Blue | — |
| `preToolUse` | `working` | Spinner | Purple | `tool` |
| `postToolUse` (success) | `tool_ok` | Short flash | Green | `tool`, `result` |
| `postToolUseFailure` | `tool_error` | Red flash | Red | `tool`, `error` |
| `permissionRequest` | `working` | Spinner | Purple | `tool` |
| `subagentStart` | `subagent_active` | Chase | Purple | `agent` |
| `subagentStop` | `idle` | Return to idle | — | `agent` |
| `agentStop` | `agent_idle` | Dim breathing | White (dim) | `reason` |
| `preCompact` | `compacting` | Wipe | Cyan | — |
| `errorOccurred` | `error` | Flash (long) | Red | `error`, `recoverable` |
| `sessionEnd` | `off` | Off | — | `reason` |
| `notification` | `notify` | Flash | White | `notification_type`, `message` |

---

## Example normalized messages

These are the exact JSON Lines the host bridge sends over serial. Each is a single line terminated by `\n`.

### Session lifecycle

```json
{"event":"sessionStart","state":"session_start"}
```

```json
{"event":"sessionEnd","state":"off","reason":"user_exit"}
```

### User input

```json
{"event":"userPromptSubmitted","state":"prompt_submitted"}
```

### Tool usage

```json
{"event":"preToolUse","state":"working","tool":"edit"}
```

```json
{"event":"postToolUse","state":"tool_ok","tool":"edit","result":"success"}
```

```json
{"event":"postToolUseFailure","state":"tool_error","tool":"bash","error":"Command failed"}
```

### Permissions

```json
{"event":"permissionRequest","state":"working","tool":"bash"}
```

### Sub-agents

```json
{"event":"subagentStart","state":"subagent_active","agent":"reviewer"}
```

```json
{"event":"subagentStop","state":"idle","agent":"reviewer"}
```

### Agent completion

```json
{"event":"agentStop","state":"agent_idle","reason":"end_turn"}
```

### Context compaction

```json
{"event":"preCompact","state":"compacting"}
```

### Errors

```json
{"event":"errorOccurred","state":"error","error":"model_error","recoverable":true}
```

---

## Required and optional fields

### Required fields (every message)

| Field | Type | Description |
|-------|------|-------------|
| `event` | string | Original Copilot hook event name (camelCase) |
| `state` | string | Normalized semantic state for firmware |

### Optional fields (included when available)

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Tool name (e.g. `bash`, `edit`, `grep`) |
| `result` | string | Tool execution result |
| `agent` | string | Sub-agent name |
| `trigger` | string | What triggered the event |
| `reason` | string | Reason for state change |
| `error` | string | Error description |
| `recoverable` | boolean | Whether the error is recoverable |
| `notification_type` | string | Type of notification |
| `message` | string | Notification message |
| `sessionId` | string | Session identifier |
| `timestamp` | string | ISO 8601 timestamp |

---

## Important: stdout cleanliness

The `preToolUse` and `permissionRequest` hooks are special — **Copilot CLI interprets JSON written to stdout as control output** (e.g. permission decisions).

The Copilot Command Ring hook **must not write anything to stdout**. All logging goes to stderr. If the hook accidentally prints to stdout during these events, Copilot CLI may misinterpret it and behave unexpectedly.

To debug hook output, use:

```bash
COPILOT_RING_LOG_LEVEL=DEBUG
```

This sends diagnostic output to **stderr only**.

---

## Protocol rules

1. Every message must end with a newline (`\n`).
2. Unknown keys in messages must be ignored by firmware.
3. Unknown `state` values must not crash firmware — fall back to idle/off.
4. The host must exit quickly (target < 1 second total hook runtime).
5. If no serial device is found, the hook exits silently — it must never block Copilot CLI.
