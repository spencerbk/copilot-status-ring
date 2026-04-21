# Setup — Windows

Step-by-step guide to set up the Copilot Command Ring on Windows.

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

> **Recommended:** Create a virtual environment first so the CLI lands on your PATH:
>
> ```powershell
> py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
> ```
>
> Once the venv is active, use `python` and `pip` directly — the `py` launcher bypasses the venv.

```powershell
pip install git+https://github.com/spencerbk/copilot-status-ring.git
```

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
   - `Arduino Uno (COM3)`
5. Note the **COM port number** (e.g. `COM7`).

> **Tip:** If you don't see a port, try a different USB cable. Charge-only cables won't work — you need a data cable.

---

## 4. Configure the serial port

The host bridge auto-detects your board by scanning for USB serial devices matching known descriptions. On boards with dual CDC channels (like CircuitPython boards), it automatically selects the correct data channel. **Most users need no port configuration.**

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
  "brightness": 0.04
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
6. The board reboots automatically. The ring should show a purple wipe animation on startup, confirming the firmware is running.

> **Note:** After copying `boot.py`, you must **unplug and replug** the board so the USB CDC data channel activates and the device appears as "Copilot Command Ring" in Device Manager. The COM port number may change.

---

## 6. Activate the ring

**Option A — Global setup (recommended, one-time):**

```powershell
copilot-command-ring setup
```

This installs hooks to `~/.copilot/hooks/` so the ring works in **every** repository automatically.

**Option B — Per-repo deploy:**

```powershell
copilot-command-ring deploy C:\code\my-project
```

This creates `.github/hooks/copilot-command-ring.json`, `run-hook.ps1`, and `run-hook.sh` in the target repo. Repeat for each repo.

---

## 7. Test with dry-run simulation

Run the simulator to verify the host bridge works without a connected device:

```powershell
python -m copilot_command_ring.simulate --dry-run
```

This sends a sequence of test events and prints the serial messages that *would* be sent. You should see JSON Lines like:

```
{"event":"sessionStart","state":"session_start"}
{"event":"preToolUse","state":"working","tool":"bash"}
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

| Variable | Description | Example |
|----------|-------------|---------|
| `COPILOT_RING_PORT` | Serial port | `COM7` |
| `COPILOT_RING_BAUD` | Baud rate (Arduino only) | `115200` |
| `COPILOT_RING_BRIGHTNESS` | LED brightness (0.0–1.0) | `0.04` |
| `COPILOT_RING_LOG_LEVEL` | Log verbosity | `DEBUG` |
| `COPILOT_RING_DRY_RUN` | Skip serial send | `1` |
| `COPILOT_RING_LOCK_TIMEOUT` | Multi-session serial lock wait (seconds) | `1.0` |
