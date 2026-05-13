# Troubleshooting

Common issues and solutions for the Copilot Command Ring.

## Contents

- [Symptom index](#symptom-index)
- [Start with these checks](#start-with-these-checks)
- ["No serial port detected"](#no-serial-port-detected)
- [`copilot-command-ring: command not found`](#copilot-command-ring-command-not-found)
- ["pyserial not installed"](#pyserial-not-installed)
- [Hooks not firing](#hooks-not-firing)
- [Ring doesn't light up](#ring-doesnt-light-up)
- [Ring becomes unresponsive after long sessions](#ring-becomes-unresponsive-after-long-sessions)
- [MicroPython-specific issues](#micropython-specific-issues)
- [Ring appears offline / hook silently doing nothing](#ring-appears-offline--hook-silently-doing-nothing)
- [Animations look wrong](#animations-look-wrong)
- [Permission denied on serial port](#permission-denied-on-serial-port)
- [Hook causes Copilot errors](#hook-causes-copilot-errors)
- [Multiple serial devices detected](#multiple-serial-devices-detected)
- [Multiple Copilot CLI sessions](#multiple-copilot-cli-sessions)
- [Still stuck?](#still-stuck)

---

## Symptom index

If you already know what is failing, start here:

| Symptom | Start here |
|---------|------------|
| Host says no port was found, or the ring warning says it may be offline | ["No serial port detected"](#no-serial-port-detected) and [Ring appears offline / hook silently doing nothing](#ring-appears-offline--hook-silently-doing-nothing) |
| `copilot-command-ring: command not found` | [`copilot-command-ring: command not found`](#copilot-command-ring-command-not-found) |
| `pyserial` import or install errors | ["pyserial not installed"](#pyserial-not-installed) |
| Copilot CLI runs, but the ring never changes | [Hooks not firing](#hooks-not-firing), then [Ring doesn't light up](#ring-doesnt-light-up) |
| The startup wipe never appears | [Ring doesn't light up](#ring-doesnt-light-up) |
| The ring works at first, then freezes, goes dark, or stays on an old state | [Ring becomes unresponsive after long sessions](#ring-becomes-unresponsive-after-long-sessions) |
| MicroPython CDC, `NEOPIXEL_PIN`, ESP32-C3/C6, or `mpremote` problems | [MicroPython-specific issues](#micropython-specific-issues) |
| Permission denied opening a serial port | [Permission denied on serial port](#permission-denied-on-serial-port) |
| Copilot CLI reports hook/control-output errors | [Hook causes Copilot errors](#hook-causes-copilot-errors) |
| Multiple terminals or repositories are sharing one ring | [Multiple Copilot CLI sessions](#multiple-copilot-cli-sessions) |

---

## Start with these checks

If you are not sure where the problem is, check the four layers in this order:

1. **Hooks installed:** On macOS/Linux, run `./install.sh` from a local clone. For manual installs, run `copilot-command-ring setup` for global hooks, or `copilot-command-ring deploy <path>` for one repo.
2. **Host can send:** Run `python -m copilot_command_ring.simulate --dry-run` and confirm JSON Lines are printed.
3. **Serial port visible:** Check Device Manager, `/dev/cu.*`, or `/dev/ttyACM*` and set `COPILOT_RING_PORT` if auto-detect picks the wrong device.
4. **Firmware running:** Reset the board and confirm the startup wipe appears before testing Copilot CLI hooks.

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

## `copilot-command-ring: command not found`

The host bridge CLI is not installed in the active shell environment, or the
venv that contains it is not active.

On macOS/Linux, the preferred fix is to use the bootstrap installer from a local
clone:

```bash
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
./install.sh
```

The installer creates a dedicated venv and installs hooks with the exact venv
Python path, so `copilot-command-ring` does not need to stay on your shell
`PATH` after setup.

If you already installed manually, either activate the venv before running the
CLI:

```bash
source .venv/bin/activate
copilot-command-ring setup
```

Or run the command directly from the venv:

```bash
.venv/bin/copilot-command-ring setup
```

---

## "pyserial not installed"

The installed host bridge depends on `pyserial`. Reinstall or upgrade
`copilot-command-ring` so pip installs the dependency automatically.

```powershell
# Windows (venv active)
pip install --upgrade git+https://github.com/spencerbk/copilot-status-ring.git
```

```bash
# macOS / Linux (venv active)
pip install --upgrade git+https://github.com/spencerbk/copilot-status-ring.git
```

If you're working from a local clone instead of a Git install:

```bash
pip install -e .
```

> **Note:** If not using a virtual environment, substitute `py -3 -m pip` (Windows) or `pip3` (macOS/Linux).

---

## Hooks not firing

The ring doesn't respond when you use Copilot CLI.

**Check that hooks are installed:**

Hooks can be installed globally (works in all repos) or per-repo:

```bash
# macOS / Linux installer (recommended)
./install.sh

# Global setup (recommended — one-time, works everywhere)
copilot-command-ring setup

# Or per-repo deploy
copilot-command-ring deploy /path/to/your-repo
```

```powershell
# Global setup (recommended — one-time, works everywhere)
copilot-command-ring setup

# Or per-repo deploy
copilot-command-ring deploy C:\path\to\your-repo
```

Verify hooks exist:

```bash
ls ~/.copilot/hooks/copilot-command-ring.json        # global
ls .github/hooks/copilot-command-ring.json            # per-repo
```

**Check Copilot CLI version:**

Hook support requires a recent version of GitHub Copilot CLI. Update it using the
same installation method you used originally.

**Reinstalled or moved your virtual environment?**

The hook scripts record the path to the Python interpreter that was active when you ran `setup` or `deploy`. If you delete and recreate the venv, or install on a new machine, the recorded path becomes stale. Re-run the installer or hook install command you used:

```bash
# macOS / Linux installer
./install.sh

# Global hooks
copilot-command-ring setup --force

# Per-repo hooks
copilot-command-ring deploy /path/to/your-repo --force
```

If the hooks can't find any Python runner, they now print a diagnostic to stderr:
`copilot-command-ring: no runner found; rerun setup/deploy`

**Check that wrapper scripts are executable (macOS/Linux):**

```bash
# Global hooks
chmod +x ~/.copilot/hooks/run-hook.sh

# Per-repo hooks
chmod +x .github/hooks/run-hook.sh
```

**Test the hook manually:**

```bash
echo '{"toolName":"bash"}' | copilot-command-ring hook preToolUse
```

If this sends data to the ring (or prints in dry-run mode), the hook itself works — the issue is with Copilot CLI loading it.

---

## Ring doesn't light up

The firmware may not be running or the wiring may be wrong.

**Check firmware is running:**

- Is the `CIRCUITPY` drive visible? If so, CircuitPython is running.
- Open a serial console (e.g. PuTTY, `screen`, or Mu Editor) to the **console** port and check for errors.
- Press Ctrl+C in the serial console to get a REPL prompt — if you get `>>>`, CircuitPython is running.
- **MicroPython boards:** Connect with `mpremote` and press Ctrl+C to get a `>>>` REPL prompt. If you get a prompt, MicroPython is running. Check for import errors by running `import main` manually.

**Check wiring:**

- Is the data pin connected through a 330 Ω resistor to the ring's DIN?
- Is the ring getting 5V power?
- Are all GNDs connected together?
- See [the hardware guide](hardware.md) for the wiring diagram.

**Check brightness:**

If brightness is set to `0`, the LEDs won't be visible. Check your config:

```bash
echo $COPILOT_RING_BRIGHTNESS
```

Default brightness is `0.04`. Try setting it higher:

```bash
export COPILOT_RING_BRIGHTNESS=0.15
```

---

## Ring becomes unresponsive after long sessions

If the ring appears stuck (frozen spinner, last-seen state lingering, or unresponsive to new events) during a long session, update the firmware variant you flashed: CircuitPython, MicroPython, or Arduino. Older firmware could go fully dark on `sessionEnd` and stay that way until power-cycle; current firmware variants instead breathe indefinitely by default and self-heal from wedged serial channels.

Recent firmware variants include several safeguards for long-running sessions:

- `sessionEnd` and stale-session pruning fall back to a dim breathing animation instead of going dark. The ring only turns fully off when the host config sets `idle_mode` to `"off"`.
- Per-state TTL decay: a crashed session stuck on `working` or `awaiting_permission` automatically decays to `agent_idle` after a few minutes, even if no further messages arrive.
- Serial-silence watchdog: if active sessions exist but the firmware receives zero bytes for 10 minutes, it reloads to recover from a wedged USB CDC channel (common on Windows with USB selective suspend).
- A capped byte buffer so malformed or partial serial data without a newline cannot grow forever in RAM.
- Draining all queued JSON lines each loop so valid traffic cannot backlog indefinitely in memory.
- Reading buffered serial data regardless of USB connection state so messages are never lost between rapid hook invocations.
- Clearing stale partial input only on USB reconnect (not on momentary disconnects between hook calls).
- Running `gc.collect()` after serial parsing work to reclaim memory from parsed JSON dicts.
- Using a watchdog plus firmware reload path so repeated loop failures recover automatically.

**Windows USB selective suspend:** Windows aggressively suspends idle USB devices, which can wedge the CDC data channel. The firmware silence watchdog detects and recovers from this. To prevent it entirely, open **Device Manager → Universal Serial Bus controllers**, right-click each **USB Root Hub**, choose **Properties → Power Management**, and uncheck *Allow the computer to turn off this device to save power*.

**If you may be running older firmware:**

1. Copy the latest firmware files for the runtime you use:
   - **CircuitPython:** `firmware/circuitpython/boot.py` and `firmware/circuitpython/code.py`
   - **MicroPython:** `firmware/micropython/boot.py`, `ring_cdc.py`, `neopixel_compat.py`, and `main.py`
   - **Arduino:** upload the latest `firmware/arduino/copilot_command_ring` sketch
2. Reset or power-cycle the board.
3. Re-test with a normal Copilot CLI session.

**If it still happens:**

- **CircuitPython:** Open the console port and look for a `MemoryError` traceback. Check that `neopixel.mpy` matches your installed CircuitPython version.
- **MicroPython:** Connect with `mpremote`, press Ctrl+C, and run `import main` to surface startup errors.
- **Arduino:** Open the serial monitor and reset the board to inspect startup output.
- If you changed the firmware, confirm there are no extra debug prints or large buffers added to the firmware file.

---

## MicroPython-specific issues

**CDC data channel not appearing:**

On MicroPython boards, the second CDC channel (used for ring communication) requires `micropython-lib`'s `usb-device-cdc` package. If the channel doesn't appear:

1. Verify MicroPython 1.24+ is installed: connect with `mpremote` and check the REPL banner version.
2. Install the package: `mpremote mip install usb-device-cdc`
3. Verify `boot.py` is on the board: `mpremote ls`
4. Unplug and replug the board — the CDC channel registers during `boot.py` execution, before `main.py` runs.

**Startup error: `Cannot detect NeoPixel pin`:**

The MicroPython firmware only auto-detects RP2040/RP2350-family boards that wire the ring to GPIO 6 by default. On QT Py RP2040 and ESP32 variants, edit `NEOPIXEL_PIN` at the top of `main.py` and set it to the GPIO number for the pin you wired before resetting.

**ESP32-C3/C6 degraded mode:**

ESP32-C3 and ESP32-C6 boards lack native USB device hardware and cannot create a custom CDC endpoint. The MicroPython firmware falls back to reading from `sys.stdin`, which shares the REPL channel. This means:

- The ring works, but REPL echoes may inject garbage into the serial stream.
- The firmware's JSON parser discards malformed lines, so brief visual glitches are the worst case.
- Avoid interacting with the REPL (Ctrl+C, typing commands) while the ring is running.

**Spinner pauses, then jumps ahead:**

Use the current `firmware/micropython/main.py` and `firmware/micropython/neopixel_compat.py` files. The MicroPython firmware keeps serial reads bounded and avoids per-frame brightness rescaling so elapsed-time animations do not visibly catch up after a loop stall. If the issue persists on ESP32-C3/C6 degraded mode, avoid REPL interaction while the ring is running or use a board with a dedicated CDC data channel.

**`mpremote` can't connect:**

- Ensure no other program (serial monitor, PuTTY) has the port open.
- On Linux, verify you're in the `dialout` group.
- Try `mpremote connect auto` or specify the port explicitly: `mpremote connect /dev/ttyACM0`.

---

## Ring appears offline / hook silently doing nothing

Copilot hooks are fire-and-forget — individual send failures are logged at `DEBUG` level and suppressed by default so they never block the CLI. If the ring seems offline, you may see no output at all at the default log level.

The host bridge now surfaces a one-shot stderr `WARNING` after three consecutive send failures, so persistent breakage becomes visible without needing to change the log level:

```text
[copilot-command-ring] WARNING: 3 consecutive send failures — ring may be offline. Run with COPILOT_RING_LOG_LEVEL=DEBUG for details.
```

If you see this, run a Copilot CLI session with `COPILOT_RING_LOG_LEVEL=DEBUG` to see the full error (port not detected, lock timeout, `SerialException`, etc.). The warning fires once per streak; a successful send resets the counter.

---

## Animations look wrong

LEDs are lighting up but the patterns are incorrect.

**Check pixel count:**

The host bridge sends `pixel_count` to the firmware in every message and the firmware applies it at runtime, so you don't need to reflash for a different ring size. The easiest way to set it is the setup wizard (`setup-status-ring`), which prompts for 24 / 16 / 12 LEDs and writes the choice into `.copilot-command-ring.local.json`. You can also set `pixel_count` directly in that file or via the `COPILOT_RING_PIXEL_COUNT` environment variable. The spinner segment auto-scales to ~25 % of the ring (with a 2-LED floor), so only the ring size needs to match — animations adapt automatically.

The firmware-default `NUM_PIXELS` (CircuitPython, MicroPython) and `PIXEL_COUNT` (Arduino) is `24`, used only for the startup wipe before the first host message arrives. On a 16- or 12-LED ring the wipe still works, but for a perfectly clean boot animation, edit that constant in firmware to match your ring before flashing.

**Check data pin:**

Make sure the data pin in the firmware matches the pin you've wired. The CircuitPython firmware auto-detects the correct pin for supported boards (e.g. `board.GP6` on Pico, `board.D6` on Feather/XIAO, `board.A0` on QT Py). The MicroPython firmware auto-detects only RP2040/RP2350-family boards wired to GPIO 6; other boards require a manual `NEOPIXEL_PIN` override in `main.py`. See [the hardware guide](hardware.md) for the full pin table.

**Check color order:**

Most NeoPixel rings use GRB color order. If colors appear swapped (e.g. red when it should be green), check the color order setting in the firmware.

**Unexpected white flashes while the ring should stay busy:**

The firmware now suppresses `notification` flashes while the winning state is `working`, `subagent_active`, or `compacting`. If you still see white flashes during active work, enable debug logging and inspect which events are being sent:

```bash
export COPILOT_RING_LOG_LEVEL=DEBUG
```

Look for `notification` payloads in the hook debug output. If the flash is caused by some other state transition, that output will show which event to trace next.

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

**Fix:** Ensure the hook writes nothing to stdout. All diagnostic output goes to stderr. If this starts after upgrading the package, re-run `copilot-command-ring setup --force` (or `deploy --force` for per-repo hooks) so the wrapper scripts match the installed code.

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

Auto-detection checks each serial device description against `device_match.description_contains` using case-insensitive substring matches. Narrow this list if another serial device is selected before the ring, or set `serial_port` for a fixed override.

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

The host bridge tags every serial message with a session identifier. Current Copilot CLI payloads provide a stable `sessionId`, which the host prefers; hook wrappers fall back to a parent-process-derived ID for older or empty payloads. All firmware variants maintain a lightweight session table and resolve the **highest-priority** state across active sessions. A system-wide file lock ensures concurrent hook processes never corrupt each other's serial writes.

**Priority order** (highest → lowest):

`error` → `awaiting_elicitation` → `awaiting_permission` → `working` → `subagent_active` → `compacting` → `prompt_submitted` → `session_start` → `agent_idle` → `idle` → `off`

**What to expect:**

- ✅ No crashes, corrupted writes, or silent failures.
- ✅ Each session's events reach the ring intact.
- ✅ The ring displays the most "interesting" state across all active sessions — for example, if one session is working and another is idle, the ring shows the working spinner.
- ✅ When a session ends, the ring seamlessly continues showing the remaining sessions' state instead of going dark.
- ⚠️ The ring cannot display two sessions simultaneously as separate animations — it shows the single highest-priority state.
- ⚠️ If a Copilot CLI crashes without sending `sessionEnd`, the firmware prunes the stale session after 5 minutes. Once all sessions are pruned — or when a session ends explicitly with `sessionEnd` — the ring shows a dim breathing animation (`agent_idle`) indefinitely so it is never dark by surprise. The next Copilot session lights it back up instantly. To revert to the pre-v1.2 behavior where `sessionEnd` turns the ring fully dark, set `"idle_mode": "off"` in `.copilot-command-ring.local.json`. Power-cycling is no longer required for recovery.

**If the ring seems stuck or unresponsive during multi-session use:**

1. Enable debug logging in one session to see what events are being sent:

   ```bash
   export COPILOT_RING_LOG_LEVEL=DEBUG
   ```

2. Check that the lock is not stale. The lock file is at:
   - **Windows:** `%TEMP%\copilot-command-ring.lock`
   - **macOS / Linux:** `/tmp/copilot-command-ring.lock`

   Deleting this file is safe — a new lock is created on the next write.

3. Verify the session ID is being sent by checking for a `"session"` field in the debug output.

> **Note:** Multi-session arbitration is supported by all three firmware variants (CircuitPython, MicroPython, and Arduino).

---

## Still stuck?

1. **Enable debug logging:** Set `COPILOT_RING_LOG_LEVEL=DEBUG` and check stderr output.
2. **Test the serial connection:** Open a serial monitor (PuTTY, `screen /dev/ttyACM1 115200`, or Arduino Serial Monitor) and manually send a JSON line:

   ```json
   {"event":"sessionStart","state":"session_start"}
   ```

   The ring should respond with a white wipe animation.
3. **Run the simulator:** `python3 -m copilot_command_ring.simulate --dry-run` to verify the host bridge logic works independently of hardware.
4. **Check the firmware console:** Connect to the CircuitPython REPL console port and look for error tracebacks.
5. **MicroPython boards:** Connect with `mpremote`, press Ctrl+C, and run `import main` to see any startup errors. Check that `boot.py`, `ring_cdc.py`, `neopixel_compat.py`, and `main.py` are all present with `mpremote ls`.
