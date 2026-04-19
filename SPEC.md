# Copilot Command Ring — Implementation Plan

## Objective

Build a physical status indicator for **GitHub Copilot CLI** using the **Adafruit NeoPixel Ring (product 1586, 24 RGB LEDs)**. The system must work:

- with **CircuitPython** as the **primary firmware target**
- with **Arduino** as the **secondary firmware target**
- on **Windows** as the **primary/default host OS**
- on **macOS** and **Linux** as supported host OSes

The indicator should react to **native Copilot CLI hook events** rather than scraping terminal output.

---

## Current facts to design around

1. **Copilot CLI supports repository hook files loaded from `.github/hooks/*.json`.** For the CLI, hooks are loaded from the current working directory's repository. Command hooks can specify both `powershell` and `bash` commands, plus `cwd`, `env`, and `timeoutSec`.
2. **Copilot CLI exposes a rich hook event surface** including:
   - `sessionStart`
   - `sessionEnd`
   - `userPromptSubmitted`
   - `preToolUse`
   - `postToolUse`
   - `postToolUseFailure`
   - `agentStop`
   - `subagentStart`
   - `subagentStop`
   - `preCompact`
   - `permissionRequest`
   - `errorOccurred`
   - `notification`
3. **`preToolUse` and `permissionRequest` interpret JSON written to stdout as control output.** Therefore, the status-indicator hook path must keep **stdout empty** unless it is intentionally making a permission decision.
4. The Adafruit part linked by the user is **product 1586**, which is the **24-pixel NeoPixel ring**.
5. Adafruit NeoPixel electrical guidance still applies:
   - add a **300–500 Ω resistor** in series with the data line
   - add a **large capacitor** (typically **500–1000 µF**) across power near the ring
   - connect **ground first** and disconnect ground last
   - if powering pixels at **5V**, a **3.3V MCU ideally uses a 5V logic-level shifter** such as **74AHCT125** or **74HCT245**

---

## High-level architecture

Use a **host-side bridge** plus **USB-connected microcontroller firmware**.

**Flow:**

`Copilot CLI hooks -> host bridge script -> serial/USB transport -> microcontroller firmware -> NeoPixel ring`

### Why this architecture

- It uses **native Copilot CLI hooks**.
- It avoids brittle terminal parsing.
- It keeps OS-specific logic on the host and LED timing-sensitive logic on the microcontroller.
- It allows the same repository to support both **CircuitPython** and **Arduino** firmware with the same host-side protocol.

---

## Opinionated design decisions

### Primary host implementation language: Python

Use **Python** for the host bridge because:

- it is cross-platform
- serial support is easy with `pyserial`
- the same script can be invoked from PowerShell and Bash hooks
- JSON payload parsing is straightforward

### Primary transport: line-delimited JSON over USB serial

Use **JSON Lines** (`\n`-terminated JSON objects) over a serial port.

Example message:

```json
{"event":"preToolUse","state":"working","tool":"bash"}
```

Why:

- easy to debug with a serial monitor
- works for CircuitPython `usb_cdc.data` and Arduino `Serial`
- easy to extend without breaking old firmware

### Primary firmware mode

Use a **state machine** on the MCU. Hooks send state transitions; the MCU owns the animation loop.

That means:

- host sends **compact semantic messages**
- MCU handles frame timing and rendering
- no streaming animation frames from the host

---

## Scope

### In scope

- repo-scoped Copilot CLI hook configuration
- host bridge for Windows/macOS/Linux
- CircuitPython firmware
- Arduino firmware
- serial protocol shared by both firmware targets
- documentation and setup instructions
- local configuration for serial port selection and brightness
- basic simulation / test harness for hook payloads

### Out of scope for v1

- wireless transport
- desktop tray app / background daemon
- audio output
- cloud logging / telemetry backend
- multiple rings / multiple devices
- bi-directional tool control via hooks
- advanced permission-policy enforcement

---

## Status model

Use a small, stable visual vocabulary.

| Copilot event | Logical state | Suggested animation | Notes |
|---|---|---|---|
| `sessionStart` | `session_start` | soft white wipe | session opened or resumed |
| `userPromptSubmitted` | `prompt_submitted` | blue clockwise sweep | user submitted prompt |
| `preToolUse` | `working` | amber spinner | active tool execution |
| `postToolUse` success | `tool_ok` | short green flash | tool finished successfully |
| `postToolUseFailure` | `tool_error` | red flash | tool failed |
| `permissionRequest` | `awaiting_permission` | yellow blink | waiting on user approval |
| `subagentStart` | `subagent_active` | purple chase | delegated work started |
| `subagentStop` | `idle` | return to idle | delegated work ended |
| `agentStop` | `agent_idle` | dim white breathing | main agent completed turn |
| `preCompact` | `compacting` | cyan wipe | context compaction |
| `errorOccurred` | `error` | longer red pulse | CLI/system/model/tool error |
| `sessionEnd` | `off` | fade to off | session ended |
| `notification` | `notify` | optional overlay | optional v1.1 feature |

### Idle baseline

Default idle should be **off** or **very dim**. Make this configurable.

Recommended default for v1: **off**.

---

## Shared serial protocol

### Transport

- USB serial
- 115200 baud by default for Arduino
- CircuitPython uses `usb_cdc.data` and does not require matching UART baud in the same way, but keep host config conceptually aligned
- one JSON object per line
- UTF-8

### Required fields

Every message must include:

- `event` — original Copilot hook event name
- `state` — normalized semantic state

### Optional fields

- `tool`
- `result`
- `agent`
- `trigger`
- `reason`
- `error`
- `recoverable`
- `notification_type`
- `message`
- `sessionId`
- `timestamp`

### Example normalized messages

```json
{"event":"sessionStart","state":"session_start"}
{"event":"userPromptSubmitted","state":"prompt_submitted"}
{"event":"preToolUse","state":"working","tool":"edit"}
{"event":"postToolUse","state":"tool_ok","tool":"edit","result":"success"}
{"event":"postToolUseFailure","state":"tool_error","tool":"bash","error":"Command failed"}
{"event":"permissionRequest","state":"awaiting_permission","tool":"bash"}
{"event":"subagentStart","state":"subagent_active","agent":"reviewer"}
{"event":"agentStop","state":"agent_idle","reason":"end_turn"}
{"event":"sessionEnd","state":"off","reason":"user_exit"}
```

### Protocol rules

- Unknown keys must be ignored by firmware.
- Unknown `state` values must not crash firmware; fall back to a safe default.
- Host must send a trailing newline for every message.
- Firmware should tolerate malformed lines by discarding them.

---

## Repo layout

Use a structure like this:

```text
copilot-command-ring/
├─ .github/
│  ├─ hooks/
│  │  ├─ copilot-command-ring.json
│  │  ├─ run-hook.ps1
│  │  └─ run-hook.sh
│  └─ copilot/
│     └─ settings.local.example.json
├─ host/
│  └─ copilot_command_ring/
│     ├─ __init__.py
│     ├─ config.py
│     ├─ constants.py
│     ├─ detect_ports.py
│     ├─ events.py
│     ├─ hook_main.py
│     ├─ protocol.py
│     ├─ sender.py
│     ├─ simulate.py
│     └─ logging_util.py
├─ firmware/
│  ├─ circuitpython/
│  │  ├─ boot.py
│  │  ├─ code.py
│  │  ├─ lib/
│  │  └─ README.md
│  └─ arduino/
│     ├─ copilot_command_ring/
│     │  └─ copilot_command_ring.ino
│     └─ README.md
├─ docs/
│  ├─ hardware.md
│  ├─ hook-events.md
│  ├─ setup-windows.md
│  ├─ setup-macos.md
│  ├─ setup-linux.md
│  └─ troubleshooting.md
├─ scripts/
│  ├─ simulate-hooks.ps1
│  └─ simulate-hooks.sh
├─ tests/
│  ├─ test_event_normalization.py
│  ├─ test_protocol.py
│  ├─ test_port_detection.py
│  └─ fixtures/
│     ├─ sessionStart.json
│     ├─ preToolUse.json
│     ├─ permissionRequest.json
│     └─ errorOccurred.json
├─ pyproject.toml
├─ requirements.txt
├─ README.md
└─ LICENSE
```

---

## Hook strategy

### Use camelCase event names

Prefer Copilot CLI's native camelCase event names in repo hook JSON.

Reason:

- they align directly with the CLI documentation
- no need to normalize snake_case VS Code-compatible payload variants for the initial hook configuration

### Hook file

Create a committed hook file at:

```text
.github/hooks/copilot-command-ring.json
```

### Command strategy

Use wrapper scripts to simplify quoting and Python discovery:

- Windows hook entries call `run-hook.ps1`
- macOS/Linux hook entries call `run-hook.sh`

The wrappers then call the Python host module.

This is more robust than embedding complex one-liners directly inside JSON.

### Important stdout rule

The hook runner path used for LED signaling must **not** emit JSON to stdout for normal operation.

Implementation requirements:

- write logs to stderr only
- return exit code `0` on success
- do not print anything to stdout in `preToolUse` or `permissionRequest` unless explicitly implementing policy control

---

## Host bridge design

### Responsibilities

The host bridge must:

1. read the hook payload JSON from stdin
2. infer which event invoked it
3. normalize the payload to a small internal event model
4. detect the target serial device
5. send a single JSON-line message to the device
6. exit quickly and quietly

### Primary invocation shape

Wrapper passes the hook event as argv[1].

Examples:

```powershell
python -m copilot_command_ring.hook_main preToolUse
```

```bash
python3 -m copilot_command_ring.hook_main preToolUse
```

### Event normalization module

Create a single `normalize_event(event_name: str, payload: dict) -> dict` function.

This function should:

- preserve the original event name in `event`
- derive `state`
- safely extract fields like `toolName`, `toolResult`, `agentName`, `trigger`, `reason`, `error`, etc.
- never throw on missing fields

### Serial device selection

Support this priority order:

1. explicit `COPILOT_RING_PORT`
2. config file value
3. auto-detect by USB VID/PID or description substring
4. first matching serial device in a filtered allowlist

#### Environment variables

Support at least:

- `COPILOT_RING_PORT`
- `COPILOT_RING_BAUD`
- `COPILOT_RING_BRIGHTNESS`
- `COPILOT_RING_LOG_LEVEL`
- `COPILOT_RING_DRY_RUN`

### Auto-detection behavior

Use `serial.tools.list_ports`.

Detect likely devices by matching one or more of:

- vendor/product IDs, if configured
- port description containing:
  - `CircuitPython`
  - `USB Serial`
  - `Arduino`
  - board-specific identifiers

If no device is found:

- fail silently by default for hook execution
- optionally log to stderr at debug level
- do not block Copilot CLI use

### Timeouts

Hook scripts must be fast.

Recommended defaults:

- serial open timeout: `0.3s`
- write timeout: `0.3s`
- total hook runtime target: `< 1s`

### Logging

Use stderr only.

Provide debug logging behind env var or config.

---

## CircuitPython firmware plan (primary)

### Primary firmware assumptions

- board has native USB
- CircuitPython is available
- `usb_cdc.data` is enabled
- `neopixel` library is available

### File set

- `boot.py`
- `code.py`

### `boot.py`

Enable USB CDC data channel:

- keep console enabled
- enable data channel

### `code.py` responsibilities

1. initialize NeoPixel ring
2. initialize serial reader on `usb_cdc.data`
3. parse line-delimited JSON
4. maintain current mode/state
5. animate in the main loop without blocking serial reading too long
6. gracefully handle malformed input

### CircuitPython animation model

Use a simple scheduler pattern:

- current state struct
- `tick(now)` called frequently
- state-specific render functions

### Required animations for v1

- off
- solid
- flash
- blink
- spinner
- wipe
- chase
- breathing

### Brightness policy

Keep default brightness low.

Recommended default: `0.06` to `0.10`

### CircuitPython implementation constraints

- avoid heavy allocation in the loop
- avoid repeated JSON parsing beyond input lines
- do not depend on threads
- do not require external storage

### CircuitPython config approach

Hard-code sane defaults in v1. Optional later: read a small JSON config file from CIRCUITPY.

---

## Arduino firmware plan (secondary)

### Primary Arduino assumptions

- board has USB serial or native USB serial
- Adafruit NeoPixel library available
- board RAM is sufficient for 24 pixels plus parsing buffer

### Arduino library

Use **Adafruit_NeoPixel**.

### Responsibilities

1. initialize `Serial`
2. initialize NeoPixel ring
3. read incoming newline-delimited JSON or a constrained pseudo-JSON parser
4. update internal state machine
5. animate in `loop()`

### Parser choice

For v1, do **not** add a heavy JSON dependency unless needed.

Use a minimal parser strategy:

- either `ArduinoJson` if target boards have adequate resources
- or a constrained string-field extractor because the host messages are tiny and predictable

Recommendation:

- use **ArduinoJson** on boards where flash/RAM are not tight
- otherwise use a tiny custom parser for only the required keys

### Arduino animation model

Match CircuitPython states semantically, not necessarily frame-for-frame.

Animations should look substantially the same across both firmware targets.

### Brightness policy

Use `setBrightness()` once during setup, not repeatedly as an animation primitive.

---

## Hardware plan

### Minimum hardware

- Adafruit NeoPixel Ring 24 (`product 1586`)
- USB-capable microcontroller that supports both CircuitPython and Arduino ideally, or at least one of them
- 300–500 Ω resistor on data line
- 500–1000 µF capacitor across 5V/GND near ring
- common ground between MCU and ring power
- optional 74AHCT125 or 74HCT245 level shifter for 3.3V MCU to 5V NeoPixel data

### Recommended wiring notes

- MCU data pin -> resistor -> ring DIN
- power supply 5V -> ring 5V
- power supply GND -> ring GND
- MCU GND -> same GND
- capacitor across ring 5V and GND near the ring

### Firmware board recommendation

Prefer a board that makes both firmware tracks easy. Example categories:

- RP2040 USB dev boards
- supported ESP32-S2/S3 USB boards
- other boards with stable CircuitPython + Arduino NeoPixel support

Do **not** hard-code one board into the architecture; keep pin/config flexible.

---

## Cross-platform host OS plan

### Windows (primary)

#### Default assumptions

- PowerShell available
- Python installed and callable as `python` or `py -3`
- serial device appears as `COMx`

#### Implementation requirements

- provide `run-hook.ps1`
- prefer `py -3` if present, otherwise `python`
- avoid requiring Bash on Windows
- document how to find the COM port in Device Manager

### macOS

#### Default assumptions

- Bash or zsh environment
- Python 3 installed
- serial device likely `/dev/cu.usbmodem*` or similar

#### Implementation requirements

- provide `run-hook.sh`
- use `python3` first, then fallback to `python`
- document granting terminal access if necessary

### Linux

#### Default assumptions

- Bash available
- Python 3 installed
- serial device likely `/dev/ttyACM*` or `/dev/ttyUSB*`

#### Implementation requirements

- provide `run-hook.sh`
- document adding the user to groups like `dialout` if serial access fails

---

## Config design

### Host config file

Provide a local, non-committed config file such as:

```text
.github/copilot/settings.local.json
```

or a project-local file such as:

```text
.copilot-command-ring.local.json
```

Recommendation: use a project-local file read by the Python host bridge, plus env var overrides.

### Config keys

Support:

```json
{
  "serial_port": "COM7",
  "baud": 115200,
  "pixel_count": 24,
  "brightness": 0.08,
  "idle_mode": "off",
  "device_match": {
    "description_contains": ["CircuitPython", "Arduino", "USB Serial"]
  }
}
```

### Override precedence

1. environment variable
2. local config file
3. built-in default

---

## Hook implementation plan

Create a single hook config JSON that registers all desired events.

### Minimum event set for v1

Implement at least:

- `sessionStart`
- `sessionEnd`
- `userPromptSubmitted`
- `preToolUse`
- `postToolUse`
- `postToolUseFailure`
- `permissionRequest`
- `subagentStart`
- `subagentStop`
- `agentStop`
- `preCompact`
- `errorOccurred`

### Optional v1.1

- `notification`

### Hook command pattern

Use wrapper scripts.

Example JSON shape:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      { "type": "command", "powershell": ".github/hooks/run-hook.ps1 sessionStart", "bash": ".github/hooks/run-hook.sh sessionStart" }
    ],
    "preToolUse": [
      { "type": "command", "powershell": ".github/hooks/run-hook.ps1 preToolUse", "bash": ".github/hooks/run-hook.sh preToolUse" }
    ]
  }
}
```

The agent should generate the full event list, not only this sample.

---

## Wrapper scripts plan

### `run-hook.ps1`

Responsibilities:

- accept event name as argument
- locate repository root
- choose Python launcher (`py -3` preferred, else `python`)
- invoke `python -m copilot_command_ring.hook_main <event>`
- pipe stdin through unchanged
- forward stderr, keep stdout clean

### `run-hook.sh`

Responsibilities:

- accept event name as argument
- resolve repo root relative to script location
- choose `python3` preferred, fallback `python`
- invoke module and pass stdin through
- keep stdout clean

---

## Detailed host normalization mapping

Use this normalized mapping.

### `sessionStart`

Output:

```json
{"event":"sessionStart","state":"session_start"}
```

### `sessionEnd`

Extract `reason`.

Output:

```json
{"event":"sessionEnd","state":"off","reason":"user_exit"}
```

### `userPromptSubmitted`

Output:

```json
{"event":"userPromptSubmitted","state":"prompt_submitted"}
```

### `preToolUse`

Extract `toolName`.

Output:

```json
{"event":"preToolUse","state":"working","tool":"edit"}
```

### `postToolUse`

Extract `toolName`, `toolResult.resultType` if present.

Output:

```json
{"event":"postToolUse","state":"tool_ok","tool":"edit","result":"success"}
```

### `postToolUseFailure`

Extract `toolName` and `error`.

Output:

```json
{"event":"postToolUseFailure","state":"tool_error","tool":"bash","error":"Command failed"}
```

### `permissionRequest`

Extract `toolName`.

Output:

```json
{"event":"permissionRequest","state":"awaiting_permission","tool":"bash"}
```

### `subagentStart`

Extract `agentName`.

Output:

```json
{"event":"subagentStart","state":"subagent_active","agent":"reviewer"}
```

### `subagentStop`

Extract `agentName`.

Output:

```json
{"event":"subagentStop","state":"idle","agent":"reviewer"}
```

### `agentStop`

Extract `stopReason`.

Output:

```json
{"event":"agentStop","state":"agent_idle","reason":"end_turn"}
```

### `preCompact`

Extract `trigger`.

Output:

```json
{"event":"preCompact","state":"compacting","trigger":"manual"}
```

### `errorOccurred`

Extract `error.name`, `error.message`, `recoverable`, `errorContext`.

Output:

```json
{"event":"errorOccurred","state":"error","error":"ToolFailure","recoverable":true}
```

### `notification` (optional)

Extract `notification_type` / `message`.

Output:

```json
{"event":"notification","state":"notify","notification_type":"permission_prompt"}
```

---

## Test strategy

### Unit tests (host)

Test:

- event normalization from real sample payloads
- protocol serialization
- config precedence
- serial port detection filters
- dry-run mode
- wrapper script behavior where practical

### Integration tests (host)

Provide simulated JSON fixtures and run:

```bash
cat tests/fixtures/preToolUse.json | python -m copilot_command_ring.hook_main preToolUse
```

Assertions:

- exits cleanly
- writes expected JSON line to a mocked serial layer
- does not write control JSON to stdout

### Firmware tests

Not traditional unit tests; use deterministic manual test sequences.

Provide host simulator scripts that send sequences like:

1. session start
2. prompt submitted
3. pre tool use
4. post tool success
5. subagent start
6. subagent stop
7. permission request
8. error occurred
9. session end

### Cross-platform validation matrix

Validate at minimum:

| Area | Windows | macOS | Linux |
|---|---|---|---|
| Hook wrapper invocation | yes | yes | yes |
| Python host bridge | yes | yes | yes |
| Serial auto-detection | yes | yes | yes |
| CircuitPython firmware | yes | yes | yes |
| Arduino firmware | yes | yes | yes |

---

## Acceptance criteria

The implementation is done when all of the following are true.

### Host-side

- A repo-scoped hook file exists and loads in Copilot CLI.
- On each supported hook event, the host script sends a normalized JSON-line message to the device.
- The host script works on Windows, macOS, and Linux.
- The host script keeps stdout empty for non-control behavior.
- The host script fails gracefully when no device is connected.

### CircuitPython firmware

- CircuitPython firmware receives serial messages and renders the required v1 animations.
- Firmware does not crash on malformed input.
- Brightness is configurable or easily editable.

### Arduino firmware

- Arduino firmware receives equivalent serial messages and renders semantically equivalent v1 animations.
- It compiles with documented board/library prerequisites.

### Documentation

- README covers architecture, setup, and supported platforms.
- Separate setup docs exist for Windows, macOS, and Linux.
- Hardware doc shows safe wiring including resistor/capacitor/common ground.
- Troubleshooting doc covers common serial-port and permission issues.

---

## Implementation order for the coding agent

Execute work in this order.

### Phase 1 — repo scaffold

1. create repo structure
2. add Python package skeleton
3. add firmware folders
4. add docs stubs

### Phase 2 — host bridge core

1. implement config loading
2. implement event normalization
3. implement serial sender
4. implement dry-run mode
5. add unit tests

### Phase 3 — hook integration

1. add `.github/hooks/copilot-command-ring.json`
2. add `run-hook.ps1`
3. add `run-hook.sh`
4. validate stdin passthrough and stdout cleanliness

### Phase 4 — CircuitPython firmware

1. add `boot.py`
2. add `code.py`
3. implement parser and state machine
4. implement required animations
5. validate against host simulator

### Phase 5 — Arduino firmware

1. implement sketch with same protocol and state names
2. implement equivalent animations
3. validate against host simulator

### Phase 6 — documentation and polish

1. write README
2. write OS setup docs
3. write hardware doc
4. write troubleshooting doc
5. add screenshots / gifs later if desired

---

## README requirements

The final README should contain:

- project summary
- hardware needed
- architecture diagram (ASCII is fine initially)
- supported OSes
- supported firmware targets
- install steps
- configuration options
- hook event mapping table
- troubleshooting section
- development / testing steps

---

## Risks and mitigations

### Risk: hook latency slows Copilot CLI

Mitigation:

- keep hook runtime sub-second
- no retries in normal path
- graceful no-device behavior
- no network calls in hook path

### Risk: serial device naming differs by OS

Mitigation:

- support explicit port env var
- add auto-detection with filters
- document manual override clearly

### Risk: accidental stdout output changes Copilot behavior

Mitigation:

- centralize logging to stderr only
- add automated test to assert stdout is empty for signal-only paths

### Risk: CircuitPython vs Arduino animations diverge

Mitigation:

- define shared semantic states first
- match semantic behavior, not exact implementation

### Risk: 3.3V data reliability with 5V NeoPixels

Mitigation:

- document recommended logic shifter
- keep wiring short
- document safe power practices

---

## Nice-to-have follow-ups

Not required for v1, but structure the code so these can be added later.

- per-tool color themes
- user-customizable themes via JSON config
- background host daemon instead of direct hook-to-serial calls
- desktop notification mirroring
- sound effects
- multiple LED devices
- support for a matrix or bar graph device
- packaging as a pip-installable tool
- prebuilt standalone binaries for Windows/macOS/Linux

---

## Deliverables the coding agent should produce

1. working Python host bridge
2. working Copilot CLI hook configuration
3. working CircuitPython firmware
4. working Arduino firmware
5. setup docs for Windows/macOS/Linux
6. hardware/wiring doc
7. tests for host event normalization and protocol behavior

---

## References the implementation should align with

- GitHub Copilot CLI hooks and hook event payloads
- GitHub Copilot CLI best practices
- Adafruit NeoPixel ring product information for product 1586
- Adafruit NeoPixel best practices for resistor, capacitor, common ground, and level shifting

---

## Final instruction to the coding agent

Build this as a **small, maintainable, cross-platform toolchain**.

Priorities, in order:

1. **correct hook integration**
2. **fast, non-intrusive host behavior**
3. **CircuitPython implementation quality**
4. **Arduino parity**
5. **clear setup docs**

Do not over-engineer v1. Ship the smallest clean implementation that:

- uses native Copilot CLI hooks
- lights the ring reliably
- works on Windows first
- also works on macOS and Linux
- supports CircuitPython first and Arduino second

