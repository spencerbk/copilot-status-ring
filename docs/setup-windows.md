# Setup — Windows

Step-by-step guide to set up the Copilot Command Ring on Windows.

## Contents

- [Recommended path](#recommended-path)
- [0. Install GitHub Copilot CLI](#0-install-github-copilot-cli)
- [1. Install Python](#1-install-python)
- [2. Install the host bridge](#2-install-the-host-bridge)
- [3. Find your COM port](#3-find-your-com-port)
- [4. Configure the serial port](#4-configure-the-serial-port)
- [5. Flash CircuitPython firmware](#5-flash-circuitpython-firmware)
- [5b. Flash MicroPython firmware (alternative)](#5b-flash-micropython-firmware-alternative)
- [6. Activate the ring](#6-activate-the-ring)
- [7. Test with dry-run simulation](#7-test-with-dry-run-simulation)
- [8. Verify hooks load in Copilot CLI](#8-verify-hooks-load-in-copilot-cli)
- [Environment variables reference](#environment-variables-reference)

---

## Recommended path

For a first build, follow the default path before customizing anything:

1. Install GitHub Copilot CLI and Python.
2. Install the host bridge in a virtual environment.
3. Flash the **CircuitPython** firmware and copy `boot.py`, `code.py`, and `neopixel.mpy`.
4. Run `copilot-command-ring setup` for global hooks.
5. Start a Copilot CLI session and confirm the ring lights up.

Set `COPILOT_RING_PORT` only if auto-detection does not find the board or selects the wrong COM port.

---

## 0. Install GitHub Copilot CLI

This project requires the **GitHub Copilot CLI** agent — the ring visualizes its activity. Follow the [Installing GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) guide to install and authenticate it. Verify it's working:

```powershell
copilot --version
```

---

## 1. Install Python

You need Python 3.9 or later. Install it using one of these methods:

**Option A — python.org installer (recommended):**

Download from [python.org/downloads](https://www.python.org/downloads/) and run the installer. **Check "Add Python to PATH"** during installation.

**Option B — winget:**

```powershell
winget install Python.Python.3.12
```

Verify it works:

```powershell
py -3 --version
```

---

## 2. Install the host bridge

> **Recommended:** Run the `/setup-status-ring` slash command from inside this
> repo when it's open in Copilot CLI. The wizard creates `.venv` next to the
> clone, installs the host bridge from local source, and deploys global hooks
> in one step. See [`docs/setup-status-ring.md`](setup-status-ring.md).

<details>
<summary><strong>Manual install (advanced)</strong></summary>

If you'd rather run the steps yourself, clone the repo and create a venv inside
it first:

```powershell
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
```

Once the venv is active, use `python` and `pip` directly — the `py` launcher
bypasses the venv. The hook install commands in step 6 record the Python path
so hooks work even outside the venv.

```powershell
pip install .
```

Or install from the GitHub URL into any environment:

```powershell
pip install git+https://github.com/spencerbk/copilot-status-ring.git
```

</details>

Verify:

```powershell
copilot-command-ring --help
```

---

## 3. Find your COM port

1. Connect your microcontroller via USB.
2. Open **Device Manager** (`devmgmt.msc`).
3. Expand **Ports (COM & LPT)**.
4. Look for your board — it will appear as something like:
   - `USB Serial Device (COM7)`
   - `CircuitPython CDC data (COM8)`
   - `MicroPython CDC (COM9)`
   - `Arduino Uno (COM3)`
5. Note the **COM port number** (e.g. `COM7`).

> **Tip:** If you don't see a port, try a different USB cable. Charge-only cables won't work — you need a data cable.

---

## 4. Configure the serial port

The host bridge auto-detects your board by scanning USB serial devices matching known descriptions. On Windows, boards with dual CDC channels (like CircuitPython boards) usually select the higher-numbered data channel automatically. **Most Windows users need no port configuration.**

If auto-detection doesn't find your board, you can set the port manually:

**Option A — environment variable (quick):**

```powershell
$env:COPILOT_RING_PORT = "COM7"
```

To make it permanent:

```powershell
[Environment]::SetEnvironmentVariable("COPILOT_RING_PORT", "COM7", "User")
```

**Option B — config file:**

Create `.copilot-command-ring.local.json` in your project root and add a `serial_port` field:

```json
{
  "serial_port": "COM7",
  "brightness": 0.04,
  "pixel_count": 24
}
```

---

## 5. Flash CircuitPython firmware

1. Download CircuitPython for your board from [circuitpython.org/downloads](https://circuitpython.org/downloads).
2. Put your board into bootloader mode (usually by double-tapping the reset button).
3. Drag the `.uf2` file onto the `RPI-RP2` (or similar) drive that appears.
4. The board reboots and a `CIRCUITPY` drive appears.
5. Copy the firmware files:
   - Copy `firmware/circuitpython/boot.py` to `CIRCUITPY/boot.py`
   - Copy `firmware/circuitpython/code.py` to `CIRCUITPY/code.py`
   - Install `neopixel.mpy` from the [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries) into `CIRCUITPY/lib/`
6. The board reboots automatically. The ring should show a magenta wipe animation on startup, confirming the firmware is running.

> **Note:** After copying `boot.py`, you must **unplug and replug** the board so the USB CDC data channel activates and the device appears as "Copilot Command Ring" in Device Manager. The COM port number may change.

---

## 5b. Flash MicroPython firmware (alternative)

Use MicroPython instead of CircuitPython if you prefer the MicroPython ecosystem.

1. Download MicroPython 1.24+ for your board from [micropython.org/download](https://micropython.org/download/).
2. Put your board into bootloader mode (double-tap reset on RP2040 boards).
3. Drag the `.uf2` file onto the boot drive that appears (e.g. `RPI-RP2`).
4. The board reboots. Install `mpremote` if it is not already available:

   ```powershell
   pip install mpremote
   ```

5. Install the USB CDC library:

   ```powershell
   mpremote mip install usb-device-cdc
   ```

6. Copy the firmware files:

   ```powershell
   mpremote cp firmware/micropython/boot.py :boot.py
   mpremote cp firmware/micropython/ring_cdc.py :ring_cdc.py
   mpremote cp firmware/micropython/neopixel_compat.py :neopixel_compat.py
   mpremote cp firmware/micropython/main.py :main.py
   ```

7. If your board does not wire NeoPixel data to GPIO 6 by default (for example QT Py RP2040 or ESP32 variants), edit `main.py` and set `NEOPIXEL_PIN` to the correct GPIO number before resetting. Then reset the board. The ring should show a magenta wipe animation on startup.

> **Note:** After the first boot with `boot.py`, the board creates a second CDC channel. Unplug and replug the board — the COM port number may change. See [`firmware/micropython/README.md`](../firmware/micropython/README.md) for board-specific details.

---

## 6. Activate the ring

**Option A — Global setup (recommended, one-time):**

```powershell
copilot-command-ring setup
```

This installs hooks to `%USERPROFILE%\.copilot\hooks` by default, or `%COPILOT_HOME%\hooks` when `COPILOT_HOME` is set, so the ring works in **every** repository automatically. The hooks record the path to your current Python, so they work even when the venv isn't active.

> **Note:** If you recreate the virtual environment or install on a new machine, re-run `copilot-command-ring setup --force` to update the recorded Python path.

**Option B — Per-repo deploy:**

```powershell
copilot-command-ring deploy C:\code\my-project
```

This creates `.github/hooks/copilot-command-ring.json`, `run-hook.ps1`, and `run-hook.sh` in the target repo. The deployed hooks record the current Python path. Repeat for each repo.

> **Note:** If you recreate the virtual environment or install on a new machine, re-run `copilot-command-ring deploy C:\code\my-project --force` in that repo to update the recorded Python path.

---

## 7. Test with dry-run simulation

Run the simulator to verify the host bridge works without a connected device:

```powershell
python -m copilot_command_ring.simulate --dry-run
```

This sends a sequence of test events and prints the serial messages that *would* be sent. You should see JSON Lines like:

```text
{"event":"sessionStart","state":"session_start","source":"new","ttl_s":60,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
{"event":"preToolUse","state":"working","tool":"bash","ttl_s":300,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
...
```

To send events to a real device:

```powershell
python -m copilot_command_ring.simulate
```

---

## 8. Verify hooks load in Copilot CLI

1. Make sure you ran `copilot-command-ring setup` (global) or `copilot-command-ring deploy <path>` (per-repo).
2. Open the Copilot CLI in a terminal inside that repository.
3. Start a session — you should see the ring light up on `sessionStart`.

If the ring doesn't respond, check:

- Did you activate hooks? (`copilot-command-ring setup` or `copilot-command-ring deploy <path>`)
- Is the COM port correct? (`$env:COPILOT_RING_PORT`)
- Is the firmware running? (Check for the `CIRCUITPY` drive)
- Run with debug logging: `$env:COPILOT_RING_LOG_LEVEL = "DEBUG"`

---

## Environment variables reference

| Variable | Default | Notes |
|----------|---------|-------|
| `COPILOT_RING_PORT` | Auto-detect | Set to `COM7` or another COM port if auto-detect selects the wrong device |
| `COPILOT_RING_BAUD` | `115200` | Serial baud rate; CircuitPython's USB CDC data channel is speed-independent |
| `COPILOT_RING_BRIGHTNESS` | `0.04` | LED brightness from `0.0` to `1.0` |
| `COPILOT_RING_PIXEL_COUNT` | `24` | Active LED count. Easiest path: pick 24 / 16 / 12 in `setup-status-ring`; alternatively set this env var or `pixel_count` in `.copilot-command-ring.local.json`. The firmware auto-scales animations to whichever ring you wire up — see [Smaller rings](#smaller-rings) below |
| `COPILOT_RING_LOG_LEVEL` | `WARNING` | Use `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `COPILOT_RING_DRY_RUN` | `false` | Set to `1`, `true`, or `yes` to skip serial sends |
| `COPILOT_RING_LOCK_TIMEOUT` | `1.0` | Seconds to wait for the multi-session serial lock |
| `COPILOT_HOME` | `%USERPROFILE%\.copilot` | Optional Copilot CLI home override; global setup installs hooks under `%COPILOT_HOME%\hooks` |

---

## Smaller rings

The 24-LED Adafruit NeoPixel Ring (product 1586) is the project default, but the 16-LED ring (product 1463) and the 12-LED ring (product 1643) are first-class targets too.

- **Easiest:** rerun `setup-status-ring` and pick 24, 16, or 12 at the *Which ring size do you have?* prompt. The wizard writes `pixel_count` into `.copilot-command-ring.local.json` for you.
- **Manually:** set `COPILOT_RING_PIXEL_COUNT` or edit `pixel_count` in your local JSON config. The host bridge sends the value to the firmware on every message and the firmware applies it at runtime — animations auto-scale.
- **Clean startup wipe:** the firmware-default `NUM_PIXELS` (CircuitPython, MicroPython) and `PIXEL_COUNT` (Arduino) is `24`, used only for the boot wipe before the first host message arrives. On a smaller ring the wipe still works, but for a perfectly clean boot animation, edit that constant in the firmware to match your ring before flashing.
