# Troubleshooting

Common issues and solutions for the Copilot Command Ring.

---

## "No serial port detected"

The host bridge can't find your microcontroller.

**Check the USB cable:**

Not all USB cables carry data. Charge-only cables are missing the D+/D− wires. Try a different cable — ideally one you've confirmed works for file transfer.

**Check that the device appears to your OS:**

```powershell
# Windows — Device Manager
devmgmt.msc
# Look under "Ports (COM & LPT)"
```

```bash
# macOS
ls /dev/cu.usbmodem*
```

```bash
# Linux
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

**Set the port explicitly:**

If auto-detect isn't finding the right device:

```powershell
# Windows
$env:COPILOT_RING_PORT = "COM7"
```

```bash
# macOS / Linux
export COPILOT_RING_PORT="/dev/ttyACM1"
```

Or create `.copilot-command-ring.local.json`:

```json
{
  "serial_port": "COM7"
}
```

---

## "pyserial not installed"

The host bridge requires `pyserial` for serial communication.

```powershell
# Windows
py -3 -m pip install pyserial
```

```bash
# macOS
pip3 install pyserial
```

```bash
# Linux
pip3 install pyserial
# or: sudo apt install python3-serial
```

Verify it's installed:

```bash
python3 -c "import serial; print(serial.VERSION)"
```

---

## Hooks not firing

The ring doesn't respond when you use Copilot CLI.

**Check the hook file exists:**

The file must be at `.github/hooks/copilot-command-ring.json` **in the repository** you're working in. Copilot CLI loads hooks from the current repo.

```bash
ls .github/hooks/copilot-command-ring.json
```

**Check Copilot CLI version:**

Hook support requires a recent version of Copilot CLI. Update to the latest version:

```bash
npm update -g @anthropic-ai/claude-code  # or your Copilot CLI package
```

**Check that wrapper scripts are executable (macOS/Linux):**

```bash
chmod +x .github/hooks/run-hook.sh
```

**Test the hook manually:**

```bash
echo '{"toolName":"bash"}' | python3 -m copilot_command_ring.hook_main preToolUse
```

If this sends data to the ring (or prints in dry-run mode), the hook itself works — the issue is with Copilot CLI loading it.

---

## Ring doesn't light up

The firmware may not be running or the wiring may be wrong.

**Check firmware is running:**

- Is the `CIRCUITPY` drive visible? If so, CircuitPython is running.
- Open a serial console (e.g. PuTTY, `screen`, or Mu Editor) to the **console** port and check for errors.
- Press Ctrl+C in the serial console to get a REPL prompt — if you get `>>>`, CircuitPython is running.

**Check wiring:**

- Is the data pin connected through a 330 Ω resistor to the ring's DIN?
- Is the ring getting 5V power?
- Are all GNDs connected together?
- See [hardware.md](hardware.md) for the wiring diagram.

**Check brightness:**

If brightness is set to `0`, the LEDs won't be visible. Check your config:

```bash
echo $COPILOT_RING_BRIGHTNESS
```

Default brightness is `0.06`–`0.10`. Try setting it higher:

```bash
export COPILOT_RING_BRIGHTNESS=0.15
```

---

## Ring becomes unresponsive after long sessions

If the Pico or other CircuitPython board stops responding and only recovers after a reset, update to the latest `firmware/circuitpython/code.py`.

Recent firmware versions include two safeguards for long-running sessions:

- A capped serial input buffer so malformed or partial JSON without a newline cannot grow forever in RAM
- Periodic `gc.collect()` calls to reduce memory pressure from repeated JSON parsing

**If you may be running older firmware:**

1. Copy the latest `firmware/circuitpython/code.py` to the `CIRCUITPY` drive.
2. Reset or power-cycle the board.
3. Re-test with a normal Copilot CLI session.

**If it still happens:**

- Open the CircuitPython console port and look for a `MemoryError` traceback.
- Check that `neopixel.mpy` matches your installed CircuitPython version.
- If you changed the firmware, confirm there are no extra debug prints or large buffers added to `code.py`.

---

## Animations look wrong

LEDs are lighting up but the patterns are incorrect.

**Check pixel count:**

The firmware is configured for 24 pixels (NeoPixel Ring product 1586). If you're using a different ring size, update the `pixel_count` in your config or firmware.

**Check data pin:**

Make sure the data pin in the firmware matches the pin you've wired. The pin name varies by board — e.g. `board.GP6` on Pico, `board.D6` on Feather/XIAO, `board.A0` on QT Py. See [`docs/hardware.md`](hardware.md) for the full pin table.

**Check color order:**

Most NeoPixel rings use GRB color order. If colors appear swapped (e.g. red when it should be green), check the color order setting in the firmware.

---

## Permission denied on serial port

**Linux — add to `dialout` group:**

```bash
sudo usermod -aG dialout $USER
```

Then **log out and log back in** (or reboot). Verify:

```bash
groups | grep dialout
```

On Arch Linux, the group may be `uucp`:

```bash
sudo usermod -aG uucp $USER
```

**macOS — check Privacy settings:**

1. Go to **System Settings → Privacy & Security**.
2. Check **USB** access (macOS 13+) and **Files and Folders** for your terminal app.
3. If using a third-party terminal (iTerm2, Alacritty), it may need explicit permission.

**Windows — driver issues:**

If the device appears in Device Manager with a warning icon:

1. Right-click the device → **Update Driver**.
2. For CircuitPython boards, no special driver is needed on Windows 10+.
3. For Arduino boards, install the Arduino IDE which includes USB drivers.

---

## Hook causes Copilot errors

The Copilot CLI is misinterpreting hook output.

**Root cause:** The `preToolUse` and `permissionRequest` hooks interpret anything written to **stdout** as a control response (e.g. a permission decision). If the hook accidentally prints to stdout, Copilot CLI may error.

**Fix:** Ensure the hook writes nothing to stdout. All diagnostic output goes to stderr.

**Debug safely:**

```powershell
# Windows
$env:COPILOT_RING_LOG_LEVEL = "DEBUG"
```

```bash
# macOS / Linux
export COPILOT_RING_LOG_LEVEL=DEBUG
```

Debug output goes to **stderr only** and won't interfere with Copilot CLI.

**Check for stray print statements:**

If you've modified the hook code, ensure there are no `print()` calls without `file=sys.stderr`.

---

## Multiple serial devices detected

If your system has multiple serial devices and the wrong one is selected:

**Set the port explicitly:**

```powershell
# Windows
$env:COPILOT_RING_PORT = "COM7"
```

```bash
# macOS / Linux
export COPILOT_RING_PORT="/dev/ttyACM1"
```

**List available ports:**

```bash
python3 -m serial.tools.list_ports -v
```

This shows all serial ports with their descriptions, which can help you identify the correct one.

**Use a config file:**

```json
{
  "serial_port": "/dev/ttyACM1",
  "device_match": {
    "description_contains": ["CircuitPython"]
  }
}
```

---

## Multiple Copilot CLI sessions

If you run Copilot CLI in multiple terminals (or across different repos) on the same machine, all sessions share the same ring.

**How it works:**

The host bridge uses a system-wide file lock so that concurrent hook processes never corrupt each other's serial writes. Each write acquires the lock, sends one JSON line, and releases it — the lock is held for only a few milliseconds.

The ring shows a **"last writer wins"** blended view: whichever session sent the most recent event determines the current animation. This means the ring may rapidly switch between states if two sessions are actively working.

**What to expect:**

- ✅ No crashes, corrupted writes, or silent failures.
- ✅ Each session's events reach the ring intact.
- ⚠️ The ring cannot display two sessions simultaneously — it shows the most recent event from any session.
- ⚠️ A `sessionEnd` from one session will turn the ring off even if another session is still active.

**If the ring seems stuck or unresponsive during multi-session use:**

1. Enable debug logging in one session to see what events are being sent:
   ```bash
   export COPILOT_RING_LOG_LEVEL=DEBUG
   ```
2. Check that the lock is not stale. The lock file is at:
   - **Windows:** `%TEMP%\copilot-command-ring.lock`
   - **macOS / Linux:** `/tmp/copilot-command-ring.lock`

   Deleting this file is safe — a new lock is created on the next write.

> **Future:** Full session-aware multiplexing (where the ring tracks all active sessions and shows priority-based state) is planned for the daemon mode in v3. See [`ROADMAP.md`](../ROADMAP.md).

---

## Still stuck?

1. **Enable debug logging:** Set `COPILOT_RING_LOG_LEVEL=DEBUG` and check stderr output.
2. **Test the serial connection:** Open a serial monitor (PuTTY, `screen /dev/ttyACM1 115200`, or Arduino Serial Monitor) and manually send a JSON line:
   ```
   {"event":"sessionStart","state":"session_start"}
   ```
   The ring should respond with a white wipe animation.
3. **Run the simulator:** `python3 -m copilot_command_ring.simulate --dry-run` to verify the host bridge logic works independently of hardware.
4. **Check the firmware console:** Connect to the CircuitPython REPL console port and look for error tracebacks.
