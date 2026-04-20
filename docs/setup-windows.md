# Setup — Windows

Step-by-step guide to set up the Copilot Command Ring on Windows.

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

## 2. Install pyserial

```powershell
py -3 -m pip install pyserial
```

Verify:

```powershell
py -3 -c "import serial; print(serial.VERSION)"
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

**Option A — environment variable (quick):**

```powershell
$env:COPILOT_RING_PORT = "COM7"
```

To make it permanent:

```powershell
[Environment]::SetEnvironmentVariable("COPILOT_RING_PORT", "COM7", "User")
```

**Option B — config file:**

Create `.copilot-command-ring.local.json` in your project root:

```json
{
  "serial_port": "COM7",
  "brightness": 0.04
}
```

**Option C — auto-detect:**

If you don't set a port, the host bridge will try to auto-detect your board by scanning for serial devices with descriptions containing "Copilot Command Ring", "CircuitPython", "Arduino", or "USB Serial".

---

## 5. Flash CircuitPython firmware

1. Download CircuitPython for your board from [circuitpython.org/downloads](https://circuitpython.org/downloads).
2. Put your board into bootloader mode (usually by double-tapping the reset button).
3. Drag the `.uf2` file onto the `RPI-RP2` (or similar) drive that appears.
4. The board reboots and a `CIRCUITPY` drive appears.
5. Copy the firmware files:
   - Copy `firmware/circuitpython/boot.py` to `CIRCUITPY/boot.py`
   - Copy `firmware/circuitpython/code.py` to `CIRCUITPY/code.py`
   - Copy `firmware/circuitpython/lib/` contents to `CIRCUITPY/lib/`
6. The board reboots automatically. The ring should show a purple wipe animation on startup, confirming the firmware is running.

> **Note:** After copying `boot.py`, you must **unplug and replug** the board so the USB CDC data channel activates and the device appears as "Copilot Command Ring" in Device Manager. The COM port number may change.

---

## 6. Test with dry-run simulation

Run the simulator to verify the host bridge works without a connected device:

```powershell
py -3 -m copilot_command_ring.simulate --dry-run
```

This sends a sequence of test events and prints the serial messages that *would* be sent. You should see JSON Lines like:

```
{"event":"sessionStart","state":"session_start"}
{"event":"preToolUse","state":"working","tool":"bash"}
...
```

To send events to a real device:

```powershell
py -3 -m copilot_command_ring.simulate
```

---

## 7. Verify hooks load in Copilot CLI

1. Make sure `.github/hooks/copilot-command-ring.json` exists in your repository.
2. Open the Copilot CLI in a terminal inside that repository.
3. Start a session — you should see the ring light up on `sessionStart`.

If the ring doesn't respond, check:

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
