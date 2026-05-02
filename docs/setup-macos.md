# Setup — macOS

Step-by-step guide to set up the Copilot Command Ring on macOS.

## Contents

- [Recommended path](#recommended-path)
- [0. Install GitHub Copilot CLI](#0-install-github-copilot-cli)
- [1. Install Python 3](#1-install-python-3)
- [2. Install the host bridge](#2-install-the-host-bridge)
- [3. Find your serial device](#3-find-your-serial-device)
- [4. Configure the serial port](#4-configure-the-serial-port)
- [5. Terminal access permissions](#5-terminal-access-permissions)
- [6. Flash CircuitPython firmware](#6-flash-circuitpython-firmware)
- [6b. Flash MicroPython firmware (alternative)](#6b-flash-micropython-firmware-alternative)
- [7. Activate the ring](#7-activate-the-ring)
- [8. Test with simulation](#8-test-with-simulation)
- [9. Verify hooks](#9-verify-hooks)
- [Environment variables reference](#environment-variables-reference)

---

## Recommended path

For a first build, follow the default path before customizing anything:

1. Install GitHub Copilot CLI and Python 3.
2. Install the host bridge in a virtual environment.
3. Flash the **CircuitPython** firmware and copy `boot.py`, `code.py`, and `neopixel.mpy`.
4. Run `copilot-command-ring setup` for global hooks.
5. Start a Copilot CLI session and confirm the ring lights up.

Set `COPILOT_RING_PORT` only if auto-detection does not find the board or selects the wrong `/dev/cu.*` device.

---

## 0. Install GitHub Copilot CLI

This project requires the **GitHub Copilot CLI** agent — the ring visualizes its activity. Follow the [Installing GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) guide to install and authenticate it. Verify it's working:

```bash
copilot --version
```

---

## 1. Install Python 3

macOS may include Python 3 already. Check:

```bash
python3 --version
```

If not installed, use Homebrew:

```bash
brew install python@3.12
```

Or download from [python.org/downloads](https://www.python.org/downloads/).

---

## 2. Install the host bridge

> **Recommended:** Create a virtual environment first:
>
> ```bash
> python3 -m venv .venv && source .venv/bin/activate
> ```
>
> The hook install commands in step 7 record the Python path so hooks work even outside the venv.

```bash
pip install git+https://github.com/spencerbk/copilot-status-ring.git
```

Verify:

```bash
copilot-command-ring --help
```

---

## 3. Find your serial device

Connect your microcontroller via USB, then list serial devices:

```bash
ls /dev/cu.usbmodem*
```

You should see something like:

```
/dev/cu.usbmodem14101
/dev/cu.usbmodem14201
```

CircuitPython boards typically create **two** serial devices — one for the REPL console and one for the data channel. The data channel is usually the **higher-numbered** one.

> **Tip:** Unplug the board, run `ls /dev/cu.*`, plug it back in, and run it again to see which devices appeared.

---

## 4. Configure the serial port

The host bridge auto-detects your board by scanning USB serial devices matching known descriptions. Unlike Windows, macOS serial listings usually do not expose USB interface numbers, so if multiple ports match you may still need to set the port manually.

If auto-detection doesn't find your board, you can set the port manually:

**Option A — environment variable:**

```bash
export COPILOT_RING_PORT="/dev/cu.usbmodem14201"
```

Add it to your shell profile (`~/.zshrc` or `~/.bashrc`) to make it permanent:

```bash
echo 'export COPILOT_RING_PORT="/dev/cu.usbmodem14201"' >> ~/.zshrc
```

**Option B — config file:**

Create `.copilot-command-ring.local.json` in your project root and add a `serial_port` field:

```json
{
  "serial_port": "/dev/cu.usbmodem14201",
  "brightness": 0.04,
  "pixel_count": 24
}
```

---

## 5. Terminal access permissions

macOS may require granting your terminal app permission to access USB devices:

1. Go to **System Settings → Privacy & Security → Files and Folders** (or **Full Disk Access**).
2. Ensure your terminal app (Terminal.app, iTerm2, etc.) has the necessary permissions.
3. If you get a "Permission denied" error when accessing the serial port, check **System Settings → Privacy & Security → USB** (macOS 13+).

---

## 6. Flash CircuitPython firmware

1. Download CircuitPython for your board from [circuitpython.org/downloads](https://circuitpython.org/downloads).
2. Put your board into bootloader mode (double-tap reset).
3. Drag the `.uf2` file onto the boot drive that appears (e.g. `RPI-RP2`).
4. The board reboots and a `CIRCUITPY` volume appears in Finder.
5. Copy the firmware files:
   ```bash
   cp firmware/circuitpython/boot.py /Volumes/CIRCUITPY/boot.py
   cp firmware/circuitpython/code.py /Volumes/CIRCUITPY/code.py
   ```
6. Install `neopixel.mpy` from the [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries) into `CIRCUITPY/lib/`.
7. The board reboots automatically.

> **Note:** After copying `boot.py`, unplug and replug the board so the USB CDC data channel activates and the device appears as "Copilot Command Ring". The device path may change.

---

## 6b. Flash MicroPython firmware (alternative)

Use MicroPython instead of CircuitPython if you prefer the MicroPython ecosystem.

1. Download MicroPython 1.24+ for your board from [micropython.org/download](https://micropython.org/download/).
2. Put your board into bootloader mode (double-tap reset on RP2040 boards).
3. Drag the `.uf2` file onto the boot drive that appears.
4. The board reboots. Install `mpremote` if it is not already available:
   ```bash
   pip install mpremote
   ```
5. Install the USB CDC library:
   ```bash
   mpremote mip install usb-device-cdc
   ```
6. Copy the firmware files:
   ```bash
   mpremote cp firmware/micropython/boot.py :boot.py
   mpremote cp firmware/micropython/ring_cdc.py :ring_cdc.py
   mpremote cp firmware/micropython/neopixel_compat.py :neopixel_compat.py
   mpremote cp firmware/micropython/main.py :main.py
   ```
7. If your board does not wire NeoPixel data to GPIO 6 by default (for example QT Py RP2040 or ESP32 variants), edit `main.py` and set `NEOPIXEL_PIN` to the correct GPIO number before resetting. Then reset the board.

> **Note:** After the first boot with `boot.py`, unplug and replug the board so the second CDC channel appears. The device path may change. See [`firmware/micropython/README.md`](../firmware/micropython/README.md) for details.

---

## 7. Activate the ring

**Option A — Global setup (recommended, one-time):**

```bash
copilot-command-ring setup
```

This installs hooks to `~/.copilot/hooks/` by default, or `$COPILOT_HOME/hooks/` when `COPILOT_HOME` is set, so the ring works in **every** repository automatically. The hooks record the path to your current Python, so they work even when the venv isn't active.

> **Note:** If you recreate the virtual environment or install on a new machine, re-run `copilot-command-ring setup --force` to update the recorded Python path.

**Option B — Per-repo deploy:**

```bash
copilot-command-ring deploy ~/code/my-project
```

> **Note:** If you recreate the virtual environment or install on a new machine, re-run `copilot-command-ring deploy ~/code/my-project --force` in that repo to update the recorded Python path.

---

## 8. Test with simulation

Run the dry-run simulator:

```bash
python3 -m copilot_command_ring.simulate --dry-run
```

You should see JSON Lines output like:

```
{"event":"sessionStart","state":"session_start","source":"new","ttl_s":60,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
{"event":"preToolUse","state":"working","tool":"bash","ttl_s":300,"idle_mode":"breathing","brightness":0.04,"pixel_count":24}
...
```

To send events to a real device:

```bash
python3 -m copilot_command_ring.simulate
```

---

## 9. Verify hooks

1. Ensure you ran `copilot-command-ring setup` (global) or `copilot-command-ring deploy <path>` (per-repo).
2. Open Copilot CLI in a terminal inside the repository.
3. Start a session — the ring should light up.

Debug if needed:

```bash
export COPILOT_RING_LOG_LEVEL=DEBUG
```

---

## Environment variables reference

| Variable | Default | Notes |
|----------|---------|-------|
| `COPILOT_RING_PORT` | Auto-detect | Set to `/dev/cu.usbmodem14201` or another device path if auto-detect selects the wrong device |
| `COPILOT_RING_BAUD` | `115200` | Serial baud rate; CircuitPython's USB CDC data channel is speed-independent |
| `COPILOT_RING_BRIGHTNESS` | `0.04` | LED brightness from `0.0` to `1.0` |
| `COPILOT_RING_PIXEL_COUNT` | `24` | Active LED count |
| `COPILOT_RING_LOG_LEVEL` | `WARNING` | Use `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `COPILOT_RING_DRY_RUN` | `false` | Set to `1`, `true`, or `yes` to skip serial sends |
| `COPILOT_RING_LOCK_TIMEOUT` | `1.0` | Seconds to wait for the multi-session serial lock |
| `COPILOT_HOME` | `~/.copilot` | Optional Copilot CLI home override; global setup installs hooks under `$COPILOT_HOME/hooks` |
