# 🟢 Copilot Command Ring

**A physical NeoPixel status ring for GitHub Copilot CLI.**

Copilot Command Ring turns an [Adafruit NeoPixel Ring (24 RGB LEDs)](https://www.adafruit.com/product/1586) into a real-time activity indicator for the Copilot CLI agent. Using native Copilot CLI hooks, it lights up when the agent is thinking, flashes on tool success or failure, blinks while waiting for permission, and fades to black when the session ends — no terminal scraping required.

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![CircuitPython](https://img.shields.io/badge/firmware-CircuitPython-blueviolet)
![MicroPython](https://img.shields.io/badge/firmware-MicroPython-2b2b2b)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Contents

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Hardware](#hardware)
- [Supported Platforms](#supported-platforms)
- [Configuration](#configuration)
- [Hook Event Mapping](#hook-event-mapping)
- [Project Structure](#project-structure)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Quick Start

### What you'll need

- **GitHub Copilot CLI** — Install by following the [Installing GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) guide. Verify it's working by running `copilot` in your terminal.
- **Python 3.9+** — Required for the host bridge. See the platform setup guides ([Windows](docs/setup-windows.md) · [macOS](docs/setup-macos.md) · [Linux](docs/setup-linux.md)) for OS-specific instructions.
- **A USB microcontroller + NeoPixel Ring** — See [Hardware](#hardware) below for the parts list, or [`docs/hardware.md`](docs/hardware.md) for wiring diagrams.

### 1. Install the host bridge

> **Recommended:** Use a virtual environment to isolate dependencies.
>
> **macOS / Linux:** `python3 -m venv .venv && source .venv/bin/activate`
> **Windows:** `py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1`
>
> Once the venv is active, use `python` and `pip` directly — the `py` launcher bypasses the venv.

```
pip install git+https://github.com/spencerbk/copilot-status-ring.git
```

Or from a local clone:

```
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
pip install .
```

### 2. Flash firmware

#### Choosing a firmware

| Feature | CircuitPython | MicroPython | Arduino |
|---------|:---:|:---:|:---:|
| Multi-session support | ✅ | ✅ | ✅ |
| NeoPixel pin auto-detect | ✅ All supported boards | ⚠️ RP2040/RP2350 only | ❌ Manual `#define` |
| Idle breathing mode | ✅ | ✅ | ✅ |
| Per-state TTL decay | ✅ | ✅ | ✅ |
| Ease of flashing | Drag-and-drop `.uf2` + file copy | `.uf2` + `mpremote` commands | Arduino IDE upload |
| **Recommended for** | Most users | MicroPython ecosystem fans | Arduino ecosystem fans |

> **Recommendation:** Use **CircuitPython** unless you have a specific reason to prefer another runtime. It has the broadest board auto-detection and the simplest setup.

**CircuitPython (recommended):**

1. Install [CircuitPython](https://circuitpython.org/downloads) on your board.
2. Copy `firmware/circuitpython/boot.py` and `firmware/circuitpython/code.py` to the `CIRCUITPY` drive.
3. Install the `neopixel` library from the [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries) into `CIRCUITPY/lib/`.

See [`firmware/circuitpython/README.md`](firmware/circuitpython/README.md) for pin auto-detection details and board-specific notes.

**MicroPython:**

1. Flash [MicroPython 1.24+](https://micropython.org/download/) onto your board.
2. Install the USB CDC library: `mpremote mip install usb-device-cdc`
3. Copy `firmware/micropython/boot.py`, `ring_cdc.py`, `main.py`, and `neopixel_compat.py` to the board using `mpremote`.
4. If your board does not wire NeoPixel data to GPIO 6 by default (for example QT Py RP2040 or ESP32 variants), set `NEOPIXEL_PIN` in `main.py` before resetting.

See [`firmware/micropython/README.md`](firmware/micropython/README.md) for board support matrix and pin configuration.

**Arduino:**

1. Open `firmware/arduino/copilot_command_ring/copilot_command_ring.ino` in the Arduino IDE.
2. Install the **Adafruit NeoPixel** library via Library Manager.
3. Upload to your board.

See [`firmware/arduino/README.md`](firmware/arduino/README.md) for board-specific pin notes and configuration options.

### 3. Activate the ring

You can activate the ring **globally** (works in every repo) or **per-repo**. Global setup is recommended.

**One-time global setup (recommended):**

```
copilot-command-ring setup
```

This installs hooks to `~/.copilot/hooks/` so the ring works in **every** repository automatically. The hooks record the current Python path, so they work even when the venv isn't active.

**Or per-repo deploy (alternative):**

```
copilot-command-ring deploy <path-to-repo>
```

This creates `.github/hooks/copilot-command-ring.json`, `run-hook.ps1`, and `run-hook.sh` in the target repo. Repeat for each repo where you want the ring active.

> **Note:** If you recreate the virtual environment or install on a new machine, re-run `setup --force` or `deploy <path> --force` to update the recorded Python path.
>
> **Tip:** The hooks auto-detect your board by USB serial description. If auto-detect picks the wrong port or finds nothing, set `COPILOT_RING_PORT` explicitly.

## How It Works

```
Copilot CLI
    │
    ▼
~/.copilot/hooks/           (global — works in all repos)
or .github/hooks/           (per-repo — optional additional install)
    │
    ▼
run-hook.ps1 / run-hook.sh
    │
    ▼
Python host bridge  ──USB serial──▶  MCU firmware  ──▶  NeoPixel Ring (24 LEDs)
(copilot_command_ring)                (CircuitPython,      (Adafruit product 1586)
                                       MicroPython,
                                       or Arduino)
```

Hook events flow from the Copilot CLI through wrapper scripts into a Python host bridge, which sends compact JSON-line messages over USB serial to the microcontroller. The MCU owns the animation loop — the host sends state transitions, not frames.

## Hardware

| Component | Details |
|-----------|---------|
| **NeoPixel Ring** | [Adafruit NeoPixel Ring 24](https://www.adafruit.com/product/1586) — 24 × WS2812B RGB LEDs |
| **Microcontroller** | Any USB-capable board: RP2040/RP2350 (Pico, XIAO), ESP32-S2/S3/C6 (QT Py, XIAO), Feather M4, etc. |
| *(optional)* **Data resistor** | 300–500 Ω in series on the NeoPixel data line |
| *(optional)* **Power capacitor** | 500–1000 µF electrolytic across NeoPixel VCC/GND |
| *(optional)* **Level shifter** | 74AHCT125 for 3.3 V boards driving 5 V NeoPixels |

> **Tip:** Connect grounds first, disconnect grounds last. See [`docs/hardware.md`](docs/hardware.md) for wiring diagrams and power guidance.

## Supported Platforms

| Layer | Primary | Also supported |
|-------|---------|----------------|
| **Host OS** | Windows | macOS, Linux |
| **Firmware** | CircuitPython | MicroPython, Arduino |

## Configuration

Configuration is resolved in this order: **environment variable > config file > default**.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COPILOT_RING_PORT` | *(auto-detect)* | Serial port (e.g., `COM7`, `/dev/ttyACM0`) |
| `COPILOT_RING_BAUD` | `115200` | Baud rate |
| `COPILOT_RING_BRIGHTNESS` | `0.04` | LED brightness (`0.0`–`1.0`) |
| `COPILOT_RING_LOG_LEVEL` | `WARNING` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `COPILOT_RING_DRY_RUN` | `false` | If `true`, log messages to stderr instead of sending to serial |
| `COPILOT_RING_LOCK_TIMEOUT` | `1.0` | Seconds to wait for the multi-session serial lock before skipping the send |

### Config File

Create `.copilot-command-ring.local.json` in the repo root (git-ignored):

```json
{
  "baud": 115200,
  "brightness": 0.04,
  "lock_timeout": 1.0,
  "idle_mode": "breathing",
  "device_match": {
    "description_contains": ["Copilot Command Ring", "CircuitPython", "MicroPython", "Arduino", "USB Serial", "Seeed"]
  }
}
```

The serial port is auto-detected by default. Add `"serial_port": "COM7"` only if auto-detection doesn't find your board.

`idle_mode` controls what the ring does when every Copilot session has ended or gone silent:

| Value | Behavior |
|-------|----------|
| `breathing` *(default)* | Ring shows a dim breathing animation indefinitely. Never goes dark on its own — the next session picks up instantly. |
| `off` | Ring goes fully dark on `sessionEnd` or stale prune. Matches the pre-v1.2 behavior. |

Unknown values are logged and normalized back to `breathing`.

## Hook Event Mapping

Each Copilot CLI hook event maps to a visual state on the ring:

| Event | State | Animation | Color |
|-------|-------|-----------|-------|
| `sessionStart` | `session_start` | wipe | warm white |
| `userPromptSubmitted` | `prompt_submitted` | wipe | blue |
| `preToolUse` | `working` | spinner | magenta |
| `preToolUse` (user-input tools, e.g. `ask_user`) | `awaiting_elicitation` | pulse | yellow |
| `postToolUse` (success) | `tool_ok` | flash | green |
| `postToolUse` (denied) | `tool_denied` | flash | amber |
| `postToolUse` (failure) | `tool_error` | flash | red |
| `postToolUseFailure` | `tool_error` | flash | red |
| `permissionRequest` | `working` | spinner | magenta |
| `subagentStart` | `subagent_active` | chase | magenta |
| `subagentStop` | `idle` | off | — |
| `agentStop` | `agent_idle` | breathing | dim white |
| `preCompact` | `compacting` | wipe | cyan |
| `errorOccurred` | `error` | flash | red |
| `notification` | `notify` | flash (suppressed while busy) | white |
| `notification` (`elicitation_dialog`) | `awaiting_elicitation` | pulse | yellow |
| `notification` (`permission_prompt`) | `awaiting_permission` | pulse | yellow |
| `sessionEnd` | `off` → `agent_idle` (breathing) | off / breathing | — |

When a `preToolUse` event fires for a tool that blocks on user input (currently `ask_user`), the host promotes it to `awaiting_elicitation` so the ring pulses yellow instead of showing the purple working spinner. For backward compatibility, the host also recognizes older `exit_plan_mode` tool events the same way.

When a `postToolUse` event includes `toolResult.resultType`, the host distinguishes `success` (green `tool_ok`), `denied` (amber `tool_denied`), and `failure` (red `tool_error`) instead of always flashing green.

When a `notification` arrives while the ring is already showing `working`, `subagent_active`, or `compacting`, the firmware keeps the busy animation instead of interrupting it with a white flash. When the notification carries `notification_type: "elicitation_dialog"`, the ring shows a persistent yellow pulse instead — signaling that the agent is blocked waiting for user input. Similarly, `notification_type: "permission_prompt"` promotes to `awaiting_permission` — this only fires when the user is actually blocked on an interactive permission dialog (not in `--yolo` mode). While that pulse is active, lower-priority transient flashes are suppressed so the ring stays yellow until the user responds; only a red `error` flash can interrupt it.

The serial protocol uses JSON Lines — one JSON object per line over USB serial. See [`docs/hook-events.md`](docs/hook-events.md) for the full protocol specification.

## Project Structure

```
copilot-status-ring/
├─ .github/hooks/                    # Copilot CLI hook config + wrapper scripts
├─ host/copilot_command_ring/        # Python host bridge
│  ├─ cli.py                         #   CLI entry point (setup, deploy, hook)
│  ├─ deploy.py                      #   Hook deployment to target repos
│  ├─ config.py                      #   Configuration loading
│  ├─ events.py                      #   Event normalization
│  ├─ protocol.py                    #   Serial protocol encoding
│  ├─ sender.py                      #   Serial port communication
│  ├─ detect_ports.py                #   Serial port auto-detection
│  ├─ serial_lock.py                 #   Multi-session serial lock
│  ├─ hook_main.py                   #   Hook event handler
│  └─ simulate.py                    #   Simulation mode
├─ firmware/circuitpython/           # CircuitPython firmware (boot.py, code.py)
├─ firmware/arduino/                 # Arduino firmware (.ino sketch)
├─ firmware/micropython/             # MicroPython firmware (boot.py, main.py, compat layer)
├─ docs/                             # Setup guides, hardware docs, troubleshooting
├─ tests/                            # pytest unit + integration tests
├─ scripts/                          # Simulation and utility scripts
├─ pyproject.toml
└─ requirements.txt
```

## Development

### Install dev dependencies

```
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
```

Create a venv (macOS / Linux: `python3 -m venv .venv && source .venv/bin/activate` · Windows: `py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1`), then:

```
pip install -e ".[dev]"
```

### Run tests

```
python -m pytest tests/ -v
```

### Lint

```
python -m ruff check host/ tests/
```

### Simulate hook events (no hardware needed)

```
python -m copilot_command_ring.simulate --dry-run
```

### Validate platform setup

```bash
bash scripts/validate-platform.sh          # macOS / Linux
.\scripts\validate-platform.ps1            # Windows
```

## Troubleshooting

Common issues and solutions are documented in [`docs/troubleshooting.md`](docs/troubleshooting.md).

Quick checks:

- **Ring not responding?** Verify the serial port with `COPILOT_RING_LOG_LEVEL=DEBUG` and check the connection.
- **No hooks firing?** Run `copilot-command-ring setup` (global) or `copilot-command-ring deploy <path>` (per-repo). See [Quick Start](#quick-start) step 3.
- **Permission errors?** Linux: add your user to the `dialout` group. macOS: check `/dev/tty.*` permissions.
- **Multiple sessions?** Fully supported across all three firmware variants. The ring shows the highest-priority state across all active sessions. Stale sessions are pruned after 5 minutes.

See also: [`docs/setup-windows.md`](docs/setup-windows.md) · [`docs/setup-macos.md`](docs/setup-macos.md) · [`docs/setup-linux.md`](docs/setup-linux.md)

## License

[MIT](LICENSE)
