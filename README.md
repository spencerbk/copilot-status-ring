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
.github/hooks/
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
| **Data resistor** *(optional)* | 300–500 Ω in series on the NeoPixel data line |
| **Power capacitor** | 500–1000 µF electrolytic across NeoPixel VCC/GND |
| **Level shifter** *(optional)* | 74AHCT125 for 3.3 V boards driving 5 V NeoPixels |

> **Tip:** Connect grounds first, disconnect grounds last. See [`docs/hardware.md`](docs/hardware.md) for wiring diagrams and power guidance.

## Supported Platforms

| Layer | Primary | Also supported |
|-------|---------|----------------|
| **Host OS** | Windows | macOS, Linux |
| **Firmware** | CircuitPython | Arduino |

## Quick Start

### 1. Clone and install

**macOS / Linux:**

```bash
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
pip3 install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
py -3 -m pip install -r requirements.txt
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

### 3. Configure the serial port

Copy the example config and set your port:

**macOS / Linux:**

```bash
cp .copilot-command-ring.local.json.example .copilot-command-ring.local.json
```

**Windows (PowerShell):**

```powershell
Copy-Item .copilot-command-ring.local.json.example .copilot-command-ring.local.json
```

Edit `.copilot-command-ring.local.json` and set `serial_port` to your board's port (e.g., `COM7` on Windows, `/dev/ttyACM0` on Linux). Or set the environment variable:

**macOS / Linux:**

```bash
export COPILOT_RING_PORT=/dev/ttyACM0
```

**Windows (PowerShell):**

```powershell
$env:COPILOT_RING_PORT = "COM7"
```

### 4. Use with Copilot CLI

The hooks in `.github/hooks/` are loaded automatically when you run Copilot CLI from this repository. No additional setup is needed — start a Copilot CLI session and the ring lights up.

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

### Config File

Create `.copilot-command-ring.local.json` in the repo root (git-ignored):

```json
{
  "serial_port": "COM7",
  "baud": 115200,
  "brightness": 0.04,
  "idle_mode": "off",
  "device_match": {
    "description_contains": ["Copilot Command Ring", "CircuitPython", "Arduino", "USB Serial"]
  }
}
```

If no port is configured, the host bridge auto-detects by matching USB device descriptions.

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
| `notification` | `notify` | flash | white |
| `sessionEnd` | `off` | off | — |

The serial protocol uses JSON Lines — one JSON object per line over USB serial. See [`docs/hook-events.md`](docs/hook-events.md) for the full protocol specification.

## Project Structure

```
copilot-status-ring/
├─ .github/hooks/                    # Copilot CLI hook config + wrapper scripts
├─ host/copilot_command_ring/        # Python host bridge
│  ├─ config.py                      #   Configuration loading
│  ├─ events.py                      #   Event normalization
│  ├─ protocol.py                    #   Serial protocol encoding
│  ├─ sender.py                      #   Serial port communication
│  ├─ hook_main.py                   #   CLI entry point
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
pip3 install -r requirements.txt
pip3 install ".[dev]"
```

**Windows (PowerShell):**

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m pip install ".[dev]"
```

### Run tests

**macOS / Linux:**

```bash
python3 -m pytest tests/ -v
```

**Windows (PowerShell):**

```powershell
py -3 -m pytest tests/ -v
```

### Lint and type-check

**macOS / Linux:**

```bash
python3 -m ruff check host/ tests/
```

**Windows (PowerShell):**

```powershell
py -3 -m ruff check host/ tests/
```

### Simulate hook events (no hardware needed)

**macOS / Linux:**

```bash
python3 -m copilot_command_ring.simulate --dry-run
```

**Windows (PowerShell):**

```powershell
py -3 -m copilot_command_ring.simulate --dry-run
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
- **No hooks firing?** Ensure you are running Copilot CLI from within this repository — hooks load from `.github/hooks/`.
- **Permission errors on serial port?** On Linux, add your user to the `dialout` group. On macOS, check `/dev/tty.*` permissions.
- **Multiple sessions?** Concurrent Copilot CLI sessions on the same machine are safe — a file lock prevents serial corruption. The ring shows a blended "last writer wins" view.

See also: [`docs/setup-windows.md`](docs/setup-windows.md) · [`docs/setup-macos.md`](docs/setup-macos.md) · [`docs/setup-linux.md`](docs/setup-linux.md)

## License

[MIT](LICENSE)
