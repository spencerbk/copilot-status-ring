# Setup — macOS

Step-by-step guide to set up the Copilot Command Ring on macOS.

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

## 2. Install pyserial

```bash
pip3 install pyserial
```

Verify:

```bash
python3 -c "import serial; print(serial.VERSION)"
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

**Option A — environment variable:**

```bash
export COPILOT_RING_PORT="/dev/cu.usbmodem14201"
```

Add it to your shell profile (`~/.zshrc` or `~/.bashrc`) to make it permanent:

```bash
echo 'export COPILOT_RING_PORT="/dev/cu.usbmodem14201"' >> ~/.zshrc
```

**Option B — config file:**

Create `.copilot-command-ring.local.json` in your project root:

```json
{
  "serial_port": "/dev/cu.usbmodem14201",
  "brightness": 0.04
}
```

**Option C — auto-detect:**

If you don't set a port, the host bridge will try to auto-detect your board by scanning for serial devices with descriptions containing "Copilot Command Ring", "CircuitPython", "Arduino", or "USB Serial".

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
   cp -r firmware/circuitpython/lib/* /Volumes/CIRCUITPY/lib/
   ```
6. The board reboots automatically.

> **Note:** After copying `boot.py`, unplug and replug the board so the USB CDC data channel activates and the device appears as "Copilot Command Ring". The device path may change.

---

## 7. Test with simulation

Run the dry-run simulator:

```bash
python3 -m copilot_command_ring.simulate --dry-run
```

You should see JSON Lines output like:

```
{"event":"sessionStart","state":"session_start"}
{"event":"preToolUse","state":"working","tool":"bash"}
...
```

To send events to a real device:

```bash
python3 -m copilot_command_ring.simulate
```

---

## 8. Verify hooks

1. Ensure `.github/hooks/copilot-command-ring.json` exists in your repo.
2. Open Copilot CLI in a terminal inside the repository.
3. Start a session — the ring should light up.

Debug if needed:

```bash
export COPILOT_RING_LOG_LEVEL=DEBUG
```

---

## Environment variables reference

| Variable | Description | Example |
|----------|-------------|---------|
| `COPILOT_RING_PORT` | Serial port | `/dev/cu.usbmodem14201` |
| `COPILOT_RING_BAUD` | Baud rate (Arduino only) | `115200` |
| `COPILOT_RING_BRIGHTNESS` | LED brightness (0.0–1.0) | `0.04` |
| `COPILOT_RING_LOG_LEVEL` | Log verbosity | `DEBUG` |
| `COPILOT_RING_DRY_RUN` | Skip serial send | `1` |
| `COPILOT_RING_LOCK_TIMEOUT` | Multi-session serial lock wait (seconds) | `1.0` |
