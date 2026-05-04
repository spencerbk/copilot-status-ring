# 🟢 Copilot Command Ring

**A physical NeoPixel status ring for developers using GitHub Copilot CLI.**

Copilot Command Ring turns an [Adafruit NeoPixel Ring (24 RGB LEDs)](https://www.adafruit.com/product/1586) into a glanceable activity indicator for the Copilot CLI agent. Native Copilot CLI hooks drive the ring directly: it lights up while the agent is thinking, flashes on tool success or failure, pulses while waiting for user input or permission, and settles into an idle breathing animation when the session ends — no terminal scraping required.

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![CircuitPython](https://img.shields.io/badge/firmware-CircuitPython-blueviolet)
![MicroPython](https://img.shields.io/badge/firmware-MicroPython-2b2b2b)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Contents

- [Quick Start](#quick-start)
- [Documentation Map](#documentation-map)
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

### Recommended first build

For the shortest path to a working ring, start with this stack:

| Area | Recommended choice | Why |
|------|--------------------|-----|
| Firmware | **CircuitPython** | Broadest board auto-detection and easiest drag-and-drop setup |
| Hooks | **One-command installer** on macOS/Linux, or global setup on Windows | One install works in every repo |
| Hardware | 24-pixel NeoPixel ring powered from the board's USB 5V pin | Matches the project defaults and stays low-current at default brightness |
| Config | Start with auto-detect; set `COPILOT_RING_PORT` only if needed | Most boards are found automatically |

The steps below follow this path. Once the ring works, use the configuration and firmware docs to customize brightness, pixel count, idle behavior, or a different firmware runtime.

### 1. Run the installer

**macOS / Linux (recommended):**

```bash
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
./install.sh
```

The installer creates a `.venv` inside the cloned repo, installs the host
bridge from your local checkout (no network install), installs global Copilot
CLI hooks, prepares the default Raspberry Pi Pico / CircuitPython firmware
files, and runs a dry-run validation. It does **not** require
`copilot-command-ring` to already be on `PATH`.

If your `CIRCUITPY` drive is already mounted, the installer can copy `boot.py`
and `code.py` there when you approve it. Otherwise it leaves prepared firmware
files under your user-level setup directory and prints the copy location.

**Windows / Copilot CLI guided setup:**

> If this repo is open in Copilot CLI, run `/setup-status-ring` for an
> interactive setup wizard. The slash command creates `<repo>/.venv` if it
> doesn't already exist, installs the host bridge from your local clone, asks
> whether hooks should apply globally or to one repo, prompts for
> board/runtime/pin choices, and attempts safe device detection before any
> firmware write. See [`docs/setup-status-ring.md`](docs/setup-status-ring.md).

<details>
<summary><strong>Manual install (advanced)</strong></summary>

The wizard handles venv creation and package install for you. If you'd rather
do it yourself — for example, to install into an existing Python environment —
run from a local clone:

```bash
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
python3 -m venv .venv          # macOS / Linux
# or: py -3 -m venv .venv       # Windows
. .venv/bin/activate           # macOS / Linux
# or: .\.venv\Scripts\Activate.ps1  # Windows
pip install .
copilot-command-ring setup
```

Or pip-install from the GitHub URL into any environment:

```bash
pip install git+https://github.com/spencerbk/copilot-status-ring.git
copilot-command-ring setup
```

</details>

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
2. Copy `boot.py` and `code.py` to the `CIRCUITPY` drive. If you ran
   `./install.sh`, use the prepared files it reported; otherwise use
   `firmware/circuitpython/boot.py` and `firmware/circuitpython/code.py`.
3. Install the `neopixel` library into `CIRCUITPY/lib/`. When `./install.sh`
   writes directly to `CIRCUITPY`, it attempts this automatically with `circup`;
   otherwise install `neopixel.mpy` from the
   [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries).

See [`firmware/circuitpython/README.md`](firmware/circuitpython/README.md) for pin auto-detection details and board-specific notes.

**MicroPython:**

1. Flash [MicroPython 1.24+](https://micropython.org/download/) onto your board.
2. Install `mpremote` if it is not already available: `pip install mpremote`
3. Install the USB CDC library: `mpremote mip install usb-device-cdc`
4. Copy `firmware/micropython/boot.py`, `ring_cdc.py`, `main.py`, and `neopixel_compat.py` to the board using `mpremote`.
5. If your board does not wire NeoPixel data to GPIO 6 by default (for example QT Py RP2040 or ESP32 variants), set `NEOPIXEL_PIN` in `main.py` before resetting.

See [`firmware/micropython/README.md`](firmware/micropython/README.md) for board support matrix and pin configuration.

**Arduino:**

1. Open `firmware/arduino/copilot_command_ring/copilot_command_ring.ino` in the Arduino IDE.
2. Install the **Adafruit NeoPixel** library via Library Manager.
3. Upload to your board.

See [`firmware/arduino/README.md`](firmware/arduino/README.md) for board-specific pin notes and configuration options.

### 3. Activate the ring

You can activate the ring **globally** (works in every repo) or **per-repo**. Global setup is recommended.

**One-time global setup (recommended):**

```bash
copilot-command-ring setup
```

This is already handled by `./install.sh`. If you installed manually, this
installs hooks to `~/.copilot/hooks/` by default, or `$COPILOT_HOME/hooks/` when
`COPILOT_HOME` is set, so the ring works in **every** repository automatically.
The hooks record the current Python path, so they work even when the venv isn't
active.

**Or per-repo deploy (alternative):**

```bash
copilot-command-ring deploy <path-to-repo>
```

This creates `.github/hooks/copilot-command-ring.json`, `run-hook.ps1`, and `run-hook.sh` in the target repo. Repeat for each repo where you want the ring active.

> **Note:** If you recreate the virtual environment or move the clone, re-run
> `/setup-status-ring` (or `./install.sh --yes`) to refresh the hook scripts —
> they embed the absolute path to the venv's Python.
>
> **Tip:** The hooks auto-detect your board by USB serial description. If auto-detect picks the wrong port or finds nothing, set `COPILOT_RING_PORT` explicitly.

## Documentation Map

| If you need to... | Go to |
|-------------------|-------|
| Wire the ring or choose a board | [`docs/hardware.md`](docs/hardware.md) |
| Set up a specific OS | [Windows](docs/setup-windows.md) · [macOS](docs/setup-macos.md) · [Linux](docs/setup-linux.md) |
| Understand hook events and serial messages | [`docs/hook-events.md`](docs/hook-events.md) |
| Diagnose setup, serial, firmware, or multi-session issues | [`docs/troubleshooting.md`](docs/troubleshooting.md) |
| Flash a specific firmware runtime | [CircuitPython](firmware/circuitpython/README.md) · [MicroPython](firmware/micropython/README.md) · [Arduino](firmware/arduino/README.md) |
| See planned work and non-goals | [`ROADMAP.md`](ROADMAP.md) |

## How It Works

```text
Copilot CLI
    │
    ▼
$COPILOT_HOME/hooks/
or ~/.copilot/hooks/        (global — works in all repos)
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

Most users can start with no configuration file. Add only the fields you need:

| Need | Recommended setting |
|------|---------------------|
| Auto-detect finds the wrong board | Set `COPILOT_RING_PORT` or `serial_port` |
| LEDs are too bright or too dim | Set `COPILOT_RING_BRIGHTNESS` or `brightness` |
| Your ring has a different LED count | Set `COPILOT_RING_PIXEL_COUNT` or `pixel_count` |
| The ring should go dark after sessions end | Set `"idle_mode": "off"` in the config file |
| Test without connected hardware | Run `python -m copilot_command_ring.simulate --dry-run`; set `COPILOT_RING_DRY_RUN=1` to make hooks skip serial sends |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COPILOT_RING_PORT` | *(auto-detect)* | Serial port (e.g., `COM7`, `/dev/ttyACM0`) |
| `COPILOT_RING_BAUD` | `115200` | Baud rate |
| `COPILOT_RING_BRIGHTNESS` | `0.04` | Runtime LED brightness (`0.0`–`1.0`) |
| `COPILOT_RING_PIXEL_COUNT` | `24` | Runtime active LED count |
| `COPILOT_RING_LOG_LEVEL` | `WARNING` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `COPILOT_RING_DRY_RUN` | `false` | Set to `1`, `true`, or `yes` to skip serial sends; the simulator prints JSON Lines |
| `COPILOT_RING_LOCK_TIMEOUT` | `1.0` | Seconds to wait for the multi-session serial lock before skipping the send |
| `COPILOT_HOME` | `~/.copilot` | Optional Copilot CLI home override; `setup` installs global hooks to `$COPILOT_HOME/hooks` |

### Config File

Create `.copilot-command-ring.local.json` in the repo root (git-ignored):

```json
{
  "baud": 115200,
  "brightness": 0.04,
  "pixel_count": 24,
  "lock_timeout": 1.0,
  "idle_mode": "breathing",
  "device_match": {
    "description_contains": ["Copilot Command Ring", "CircuitPython", "MicroPython", "Arduino", "USB Serial", "Seeed"]
  }
}
```

The serial port is auto-detected by default. Add `"serial_port": "COM7"` only if auto-detection doesn't find your board.

Auto-detection compares each serial device description against `device_match.description_contains` using case-insensitive substring matches, then prefers the highest USB interface number when multiple matching ports share a VID/PID. Narrow `description_contains` when another serial device is selected; use `serial_port` when you want a fixed override.

`idle_mode` controls what the ring does when every Copilot session has ended or gone silent:

| Value | Behavior |
|-------|----------|
| `breathing` *(default)* | Ring shows a dim breathing animation indefinitely. Never goes dark on its own — the next session picks up instantly. |
| `off` | Ring goes fully dark on `sessionEnd` or stale prune. Matches the pre-v1.2 behavior. |

Unknown values are logged and normalized back to `breathing`.

`brightness` and `pixel_count` are included in every host → firmware message. Current firmware variants apply them at runtime after the first host message arrives; the startup wipe still uses the firmware/sketch defaults until then.

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

```text
copilot-status-ring/
├─ .github/extensions/setup-status-ring/  # Copilot CLI setup wizard extension
├─ install.sh                         # macOS/Linux one-command installer
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

Per-repo hooks are generated by `copilot-command-ring deploy` under the target repository's `.github/hooks/` directory; they are not committed in this repo by default.

## Development

### Install dev dependencies

```bash
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
```

Create `.venv` inside the clone (or let `/setup-status-ring` / `./install.sh` do it for you), then install with the dev extras:

```bash
python3 -m venv .venv && source .venv/bin/activate    # macOS / Linux
# or: py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1  # Windows
pip install -e ".[dev]"
```

### Run tests

```bash
python -m pytest tests/ -v
```

### Lint

```bash
python -m ruff check host/ tests/
```

### Simulate hook events (no hardware needed)

```bash
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
- **No hooks firing?** On macOS/Linux, run `./install.sh` from a local clone. For manual installs, run `copilot-command-ring setup` (global) or `copilot-command-ring deploy <path>` (per-repo). See [Quick Start](#quick-start) step 3.
- **Permission errors?** Linux: add your user to the `dialout` group. macOS: check `/dev/tty.*` permissions.
- **Multiple sessions?** Fully supported across all three firmware variants. The ring shows the highest-priority state across all active sessions. Stale sessions are pruned after 5 minutes.

See also: [`docs/setup-windows.md`](docs/setup-windows.md) · [`docs/setup-macos.md`](docs/setup-macos.md) · [`docs/setup-linux.md`](docs/setup-linux.md)

## License

[MIT](LICENSE)
