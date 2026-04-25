# Hook Events Reference

This document describes every Copilot CLI hook event that the Copilot Command Ring handles, the serial protocol, and the normalized messages sent to the firmware.

## Contents

- [Protocol overview](#protocol-overview)
- [Event mapping table](#event-mapping-table)
- [Example normalized messages](#example-normalized-messages)
- [Required and optional fields](#required-and-optional-fields)
- [Important: stdout cleanliness](#important-stdout-cleanliness)
- [Protocol rules](#protocol-rules)

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
| `preToolUse` | `working` | Spinner | Magenta | `tool` |
| `preToolUse` (user-input tools, e.g. `ask_user`) | `awaiting_elicitation` | Pulse | Yellow | `tool` |
| `postToolUse` (success) | `tool_ok` | Short flash | Green | `tool`, `result` |
| `postToolUse` (denied) | `tool_denied` | Short flash | Amber | `tool`, `result` |
| `postToolUse` (failure) | `tool_error` | Red flash | Red | `tool`, `result` |
| `postToolUseFailure` | `tool_error` | Red flash | Red | `tool`, `error` |
| `permissionRequest` | `working` | Spinner | Magenta | `tool` |
| `subagentStart` | `subagent_active` | Chase | Magenta | `agent` |
| `subagentStop` | `idle` | Return to idle | — | `agent` |
| `agentStop` | `agent_idle` | Dim breathing | White (dim) | `reason` |
| `preCompact` | `compacting` | Wipe | Cyan | — |
| `errorOccurred` | `error` | Flash (long) | Red | `error`, `message`, `recoverable`, `errorContext` |
| `sessionEnd` | `off` (→ `agent_idle` unless `idle_mode="off"`) | Off or breathing | — | `reason` |
| `notification` | `notify` | Flash (suppressed while busy) | White | `notification_type`, `message` |
| `notification` (`elicitation_dialog`) | `awaiting_elicitation` | Pulse (smooth sine fade) | Yellow | `notification_type`, `message` |
| `notification` (`permission_prompt`) | `awaiting_permission` | Pulse (hard on/off blink) | Yellow | `notification_type`, `message` |

When a `notification` arrives with `notification_type: "elicitation_dialog"`, the host promotes it to the persistent `awaiting_elicitation` state instead of the transient `notify` flash. This signals that the agent is blocked waiting for user input (e.g. an interactive form or choice). The pulse animation uses a raised brightness floor so the ring never fully extinguishes, distinguishing it from the hard on/off blink of `awaiting_permission`. Priority is above `awaiting_permission` but below `error`, and lower-priority transient flashes are suppressed while elicitation is active so the ring keeps pulsing yellow until the user responds.

When a `notification` arrives with `notification_type: "permission_prompt"`, the host promotes it to the persistent `awaiting_permission` state. This fires only when the user is actually blocked on an interactive permission dialog — in `--yolo` mode, permissions are auto-approved and no `permission_prompt` notification is emitted. The `permissionRequest` hook event itself always maps to `working` because it fires for both interactive and auto-approved permissions.

When a generic `notification` arrives while the winning persistent state is `working`, `subagent_active`, or `compacting`, the firmware suppresses the white flash and leaves the busy animation running.

---

## Example normalized messages

These are representative JSON Lines the host bridge sends over serial. `idle_mode`, `brightness`, and `pixel_count` are injected on every message in real traffic, `ttl_s` appears on persistent states that auto-decay, and `session` is omitted below for readability. Each message is a single line terminated by `\n`.

### Session lifecycle

```json
{"event":"sessionStart","state":"session_start","source":"new","ttl_s":60,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

The `source` field indicates how the session was initiated: `"new"` (fresh session), `"resume"` (resumed from a prior context), or `"startup"` (agent auto-started). The firmware ignores this field — it is forwarded for diagnostic/logging purposes.

```json
{"event":"sessionEnd","state":"off","reason":"user_exit","idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

### User input

```json
{"event":"userPromptSubmitted","state":"prompt_submitted","ttl_s":120,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

### Tool usage

```json
{"event":"preToolUse","state":"working","tool":"edit","ttl_s":300,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

```json
{"event":"postToolUse","state":"tool_ok","tool":"edit","result":"success","idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

```json
{"event":"postToolUseFailure","state":"tool_error","tool":"bash","error":"Command failed","idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

### Tool denied by user

```json
{"event":"postToolUse","state":"tool_denied","tool":"grep","result":"denied","idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

When a `postToolUse` event carries `resultType: "denied"` in `toolResult`, the host maps it to `tool_denied` — an amber flash that distinguishes user-denied tools from successful completions. The `resultType` field supports three values:

- `"success"` (or absent) → `tool_ok` (green flash)
- `"failure"` → `tool_error` (red flash, same as `postToolUseFailure`)
- `"denied"` → `tool_denied` (amber flash)

### User-input tools (elicitation via preToolUse)

```json
{"event":"preToolUse","state":"awaiting_elicitation","tool":"ask_user","ttl_s":600,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

When a `preToolUse` event fires for a tool that blocks on user input (currently `ask_user`), the host promotes the state from `working` to `awaiting_elicitation`. This displays the yellow pulse animation instead of the purple spinner, signaling that the agent is waiting for user input rather than actively processing. The Copilot CLI `notification` mechanism with `elicitation_dialog` does not fire for these tools — the `preToolUse` tool-name check is the reliable detection path. For backward compatibility, the host also recognizes older `exit_plan_mode` tool events the same way.

### Permissions

```json
{"event":"permissionRequest","state":"working","tool":"bash","ttl_s":300,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

The `permissionRequest` hook fires for both interactive and auto-approved (yolo) permissions, so it always maps to `working`. When the user is actually blocked on a permission dialog, the Copilot CLI also emits a `notification` with `notification_type: "permission_prompt"`:

```json
{"event":"notification","state":"awaiting_permission","notification_type":"permission_prompt","message":"Edit file: foo.py","ttl_s":600,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

In `--yolo` mode, no `permission_prompt` notification is emitted — the ring stays on the purple working spinner.

### Sub-agents

```json
{"event":"subagentStart","state":"subagent_active","agent":"reviewer","ttl_s":300,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

```json
{"event":"subagentStop","state":"idle","agent":"reviewer","idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

### Agent completion

```json
{"event":"agentStop","state":"agent_idle","reason":"end_turn","idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

### Context compaction

```json
{"event":"preCompact","state":"compacting","ttl_s":300,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

### Errors

```json
{"event":"errorOccurred","state":"error","error":"RateLimitError","message":"API rate limit exceeded","recoverable":true,"errorContext":"model_request","ttl_s":60,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

### Notifications

```json
{"event":"notification","state":"notify","notification_type":"info","message":"Background task complete","idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

The host still sends the normalized `notify` message above. Busy-state suppression happens in firmware so idle sessions can still show the white notification flash.

### Elicitation dialog (user input required)

```json
{"event":"notification","state":"awaiting_elicitation","notification_type":"elicitation_dialog","message":"Choose an option","ttl_s":600,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
```

When the notification carries `notification_type: "elicitation_dialog"`, the host promotes the state to `awaiting_elicitation` — a persistent state with a 600 s TTL safety net.

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
| `session` | string | Copilot CLI session identifier. The host prefers the hook payload's `sessionId` and falls back to the wrapper-derived process ID for older or empty payloads. Enables multi-session arbitration on firmware. |
| `source` | string | How the session was initiated: `"new"`, `"resume"`, or `"startup"`. Forwarded from `sessionStart` for diagnostics. |
| `tool` | string | Tool name (e.g. `bash`, `edit`, `grep`) |
| `result` | string | Tool execution result |
| `agent` | string | Sub-agent name |
| `trigger` | string | What triggered the event |
| `reason` | string | Reason for state change |
| `error` | string | Error description |
| `errorContext` | string | Error context identifier |
| `recoverable` | boolean | Whether the error is recoverable |
| `notification_type` | string | Type of notification |
| `message` | string | Notification message |
| `ttl_s` | integer | Per-state decay window in seconds. The firmware treats a session's persistent state as `agent_idle` if no refresh arrives within this many seconds. Transient states and `agent_idle` itself have no TTL. |
| `idle_mode` | string | What the ring should do when all sessions are gone: `"breathing"` (default, dim breathing forever) or `"off"` (fully dark). Injected by the host on every message so the firmware always has a fresh value, including immediately after a reload. |
| `brightness` | number | Runtime LED brightness scalar (`0.0`–`1.0`). Injected by the host on every message and applied by current firmware variants after receipt. |
| `pixel_count` | integer | Runtime active LED count. Injected by the host on every message and applied by current firmware variants after receipt. |

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
6. When the `session` field is present, firmware uses it for multi-session state arbitration. Messages without `session` are handled with legacy single-session behavior: the last persistent untagged state remains active until another persistent state replaces it, and untagged transient states flash on top of it once.
7. `ttl_s`, `idle_mode`, `brightness`, and `pixel_count` are optional and backward compatible — firmware that predates them simply ignores the extra keys.
