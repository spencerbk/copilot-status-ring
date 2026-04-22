# 🟢 Copilot Command Ring

**A physical NeoPixel status ring for GitHub Copilot CLI.**

Copilot Command Ring turns an [Adafruit NeoPixel Ring (24 RGB LEDs)](https://www.adafruit.com/product/1586) into a real-time activity indicator for the Copilot CLI agent. Using native Copilot CLI hooks, it lights up when the agent is thinking, flashes on tool success or failure, blinks while waiting for permission, and fades to black when the session ends — no terminal scraping required.

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![CircuitPython](https://img.shields.io/badge/firmware-CircuitPython-blueviolet)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Architecture

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
(copilot_command_ring)                (CircuitPython       (Adafruit product 1586)
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
| **Firmware** | CircuitPython | Arduino |

## Prerequisites

- **GitHub Copilot CLI** — This project is a hardware companion for the Copilot CLI agent. Install it by following the [Installing GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) guide. Verify it's working by running `copilot` in your terminal.
- **Python 3.9+** — Required for the host bridge. See the platform setup guides below for installation instructions.

## Quick Start

### 1. Install the host bridge

> **Recommended:** Use a virtual environment to isolate dependencies.
>
> **macOS / Linux:** `python3 -m venv .venv && source .venv/bin/activate`
>
> **Windows (PowerShell):** `py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1`
>
> Once the venv is active, use `python` and `pip` directly — the `py` launcher bypasses the venv.
>
> The hook install commands in step 3 record the Python path so hooks work even outside the venv.

**macOS / Linux:**

```bash
pip install git+https://github.com/spencerbk/copilot-status-ring.git
```

  Or from a local clone:

  ```bash
  git clone https://github.com/spencerbk/copilot-status-ring.git
  cd copilot-status-ring
  pip install .
  ```

**Windows (PowerShell):**

```powershell
pip install git+https://github.com/spencerbk/copilot-status-ring.git
```

  Or from a local clone:

  ```powershell
  git clone https://github.com/spencerbk/copilot-status-ring.git
  cd copilot-status-ring
  pip install .
  ```

### 2. Flash firmware

**CircuitPython (recommended):**

1. Install [CircuitPython](https://circuitpython.org/downloads) on your board.
2. Copy `firmware/circuitpython/boot.py` and `firmware/circuitpython/code.py` to the `CIRCUITPY` drive.
3. Install the `neopixel` library from the [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries) into `CIRCUITPY/lib/`.

**Arduino:**

1. Open `firmware/arduino/copilot_command_ring/copilot_command_ring.ino` in the Arduino IDE.
2. Install the **Adafruit NeoPixel** library via Library Manager.
3. Upload to your board.

### 3. Activate the ring

**One-time global setup (recommended):**

```bash
copilot-command-ring setup
```

This installs hooks to `~/.copilot/hooks/` so the ring works in **every** repository automatically. The hooks record the current Python path, so they work even when the venv isn't active.

> **Note:** If you recreate the virtual environment or install on a new machine, re-run `copilot-command-ring setup --force` to update the recorded Python path.

**Or per-repo deploy (alternative):**

Run from any directory — this writes hook files into your target repo:

**macOS / Linux:**

```bash
copilot-command-ring deploy ~/code/my-project
```

**Windows (PowerShell):**

```powershell
copilot-command-ring deploy C:\code\my-project
```

This creates `.github/hooks/copilot-command-ring.json`, `run-hook.ps1`, and `run-hook.sh` in the target repo. The deployed hooks record the current Python path. Repeat for each repo where you want the ring active.

> **Note:** If you recreate the virtual environment or install on a new machine, re-run `copilot-command-ring deploy <path> --force` in that repo to update the recorded Python path.

> **Tip:** The deployed hooks auto-detect your board — no port configuration needed. Start a Copilot CLI session and the ring lights up.

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
  "idle_mode": "off",
  "device_match": {
    "description_contains": ["Copilot Command Ring", "CircuitPython", "Arduino", "USB Serial", "Seeed"]
  }
}
```

The serial port is auto-detected by default. Add `"serial_port": "COM7"` only if auto-detection doesn't find your board.

## Hook Event Mapping

Each Copilot CLI hook event maps to a visual state on the ring:

| Event | State | Animation | Color |
|-------|-------|-----------|-------|
| `sessionStart` | `session_start` | wipe | warm white |
| `userPromptSubmitted` | `prompt_submitted` | wipe | blue |
| `preToolUse` | `working` | spinner | purple |
| `postToolUse` | `tool_ok` | flash | green |
| `postToolUseFailure` | `tool_error` | flash | red |
| `permissionRequest` | `working` | spinner | purple |
| `subagentStart` | `subagent_active` | chase | magenta |
| `subagentStop` | `idle` | off | — |
| `agentStop` | `agent_idle` | breathing | dim white |
| `preCompact` | `compacting` | wipe | cyan |
| `errorOccurred` | `error` | flash | red |
| `notification` | `notify` | flash (suppressed while busy) | white |
| `sessionEnd` | `off` | off | — |

When a `notification` arrives while the ring is already showing `working`, `subagent_active`, or `compacting`, the firmware keeps the busy animation instead of interrupting it with a white flash.

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
├─ docs/                             # Setup guides, hardware docs, troubleshooting
├─ tests/                            # pytest unit + integration tests
├─ scripts/                          # Simulation and utility scripts
├─ pyproject.toml
└─ requirements.txt
```

## Development

### Install dev dependencies

**macOS / Linux:**

```bash
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### Run tests

**macOS / Linux:**

```bash
python3 -m pytest tests/ -v
```

**Windows (PowerShell):**

```powershell
python -m pytest tests/ -v
```

### Lint

**macOS / Linux:**

```bash
python3 -m ruff check host/ tests/
```

**Windows (PowerShell):**

```powershell
python -m ruff check host/ tests/
```

### Simulate hook events (no hardware needed)

**macOS / Linux:**

```bash
python3 -m copilot_command_ring.simulate --dry-run
```

**Windows (PowerShell):**

```powershell
python -m copilot_command_ring.simulate --dry-run
```

### Validate platform setup

Run the platform validation script to check that your environment is correctly configured:

**macOS / Linux:**

```bash
bash scripts/validate-platform.sh
```

**Windows (PowerShell):**

```powershell
.\scripts\validate-platform.ps1
```

## Troubleshooting

Common issues and solutions are documented in [`docs/troubleshooting.md`](docs/troubleshooting.md).

Quick checks:

- **Ring not responding?** Verify the serial port with `COPILOT_RING_LOG_LEVEL=DEBUG` and check the connection.
- **No hooks firing?** Run `copilot-command-ring setup` (global, recommended) or `copilot-command-ring deploy <path>` (per-repo). See [Quick Start](#quick-start) step 3.
- **Permission errors on serial port?** On Linux, add your user to the `dialout` group. On macOS, check `/dev/tty.*` permissions.
- **Multiple sessions?** Concurrent Copilot CLI sessions on the same machine are fully supported. The firmware tracks each session independently and displays the highest-priority state across all active sessions. When one session ends, the ring seamlessly continues showing the remaining sessions' state. If all sessions go idle (no hook events for 5 minutes), the ring transitions to a dim breathing animation and stays there until a new event arrives or an explicit `sessionEnd` turns it off — it will not go dark on its own. A file lock prevents serial corruption.

See also: [`docs/setup-windows.md`](docs/setup-windows.md) · [`docs/setup-macos.md`](docs/setup-macos.md) · [`docs/setup-linux.md`](docs/setup-linux.md)

## License

[MIT](LICENSE)
