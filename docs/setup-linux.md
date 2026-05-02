# Setup — Linux

Step-by-step guide to set up the Copilot Command Ring on Linux.

## Contents

- [Recommended path](#recommended-path)
- [0. Install GitHub Copilot CLI](#0-install-github-copilot-cli)
- [1. Install Python 3](#1-install-python-3)
- [2. Run the installer](#2-run-the-installer)
- [3. Find your serial device](#3-find-your-serial-device)
- [4. Add your user to the `dialout` group](#4-add-your-user-to-the-dialout-group)
- [5. Configure the serial port](#5-configure-the-serial-port)
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
2. Run `./install.sh` from a local clone.
3. Add your user to the serial-device group (`dialout` on most distributions).
4. Flash the **CircuitPython** UF2 if the board is not already running it.
5. Copy the prepared firmware files to `CIRCUITPY` if the installer did not copy them for you.
6. Start a Copilot CLI session and confirm the ring lights up.

Set `COPILOT_RING_PORT` only if auto-detection does not find the board or selects the wrong `/dev/tty*` device.

---

## 0. Install GitHub Copilot CLI

This project requires the **GitHub Copilot CLI** agent — the ring visualizes its activity. Follow the [Installing GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) guide to install and authenticate it. Verify it's working:

```bash
copilot --version
```

---

## 1. Install Python 3

Most Linux distributions include Python 3. Verify:

```bash
python3 --version
```

If not installed:

**Debian/Ubuntu:**

```bash
sudo apt update && sudo apt install python3 python3-pip
```

**Fedora:**

```bash
sudo dnf install python3 python3-pip
```

**Arch Linux:**

```bash
sudo pacman -S python python-pip
```

---

## 2. Run the installer

From a local clone:

```bash
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
./install.sh
```

The installer creates a dedicated user-level virtual environment, installs the
host bridge, installs global hooks, prepares CircuitPython firmware files, and
runs a dry-run validation. It does not depend on `copilot-command-ring` already
being on `PATH`.

Useful options:

```bash
./install.sh --yes
./install.sh --firmware-target /media/$USER/CIRCUITPY
./install.sh --repo ~/code/my-project
```

Manual fallback: create a venv, run `pip install git+https://github.com/spencerbk/copilot-status-ring.git`, then run `copilot-command-ring setup`.

---

## 3. Find your serial device

Connect your microcontroller via USB, then list serial devices:

```bash
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

You should see something like:

```text
/dev/ttyACM0
/dev/ttyACM1
```

- **`/dev/ttyACM*`** — typical for boards with native USB (RP2040, ESP32-S2/S3, most CircuitPython boards)
- **`/dev/ttyUSB*`** — typical for boards with a USB-to-serial chip (FTDI, CH340, CP2102)

CircuitPython boards create **two** serial devices — one for the REPL console and one for the data channel. The data channel is usually the **second** one (e.g. `/dev/ttyACM1`).

> **Tip:** Run `dmesg | tail -20` right after plugging in to see which devices were created.

---

## 4. Add your user to the `dialout` group

By default, serial ports require root access. Add your user to the `dialout` group:

```bash
sudo usermod -aG dialout $USER
```

> **Important:** You must **log out and log back in** (or reboot) for the group change to take effect.

Verify you're in the group:

```bash
groups
```

You should see `dialout` in the output.

> **Note:** On some distributions (e.g. Arch Linux), the group may be called `uucp` instead of `dialout`:
>
> ```bash
> sudo usermod -aG uucp $USER
> ```

---

## 5. Configure the serial port

The host bridge auto-detects your board by scanning USB serial devices matching known descriptions. Unlike Windows, Linux serial listings usually do not expose USB interface numbers, so if multiple ports match you may still need to set the port manually.

If auto-detection doesn't find your board, you can set the port manually:

**Option A — environment variable:**

```bash
export COPILOT_RING_PORT="/dev/ttyACM1"
```

Add it to your shell profile (`~/.bashrc` or `~/.zshrc`) to make it permanent:

```bash
echo 'export COPILOT_RING_PORT="/dev/ttyACM1"' >> ~/.bashrc
```

**Option B — config file:**

Create `.copilot-command-ring.local.json` in your project root and add a `serial_port` field:

```json
{
  "serial_port": "/dev/ttyACM1",
  "brightness": 0.04,
  "pixel_count": 24
}
```

---

## 6. Flash CircuitPython firmware

1. Download CircuitPython for your board from [circuitpython.org/downloads](https://circuitpython.org/downloads).
2. Put your board into bootloader mode (double-tap reset).
3. Mount the boot drive if it doesn't auto-mount:

   ```bash
   # Check where it mounted
   lsblk
   # Or mount manually
   sudo mount /dev/sda1 /mnt
   ```

4. Copy the `.uf2` file to the boot drive:

   ```bash
   cp circuitpython-*.uf2 /media/$USER/RPI-RP2/
   ```

5. The board reboots and a `CIRCUITPY` volume appears.
6. Copy the firmware files:

   ```bash
   # Use the path printed by ./install.sh when available:
   cp ~/.local/share/copilot-command-ring/firmware/circuitpython/boot.py /media/$USER/CIRCUITPY/boot.py
   cp ~/.local/share/copilot-command-ring/firmware/circuitpython/code.py /media/$USER/CIRCUITPY/code.py
   sync
   ```

7. Install `neopixel.mpy` from the [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries) into `CIRCUITPY/lib/` if the installer did not already install it with `circup`.
8. The board reboots automatically.

> **Note:** After copying `boot.py`, unplug and replug the board so the USB CDC data channel activates and the device appears as "Copilot Command Ring". The device path may change.

---

## 6b. Flash MicroPython firmware (alternative)

Use MicroPython instead of CircuitPython if you prefer the MicroPython ecosystem.

1. Download MicroPython 1.24+ for your board from [micropython.org/download](https://micropython.org/download/).
2. Put your board into bootloader mode (double-tap reset on RP2040 boards).
3. Copy the `.uf2` file to the boot drive:

   ```bash
   cp micropython-*.uf2 /media/$USER/RPI-RP2/
   ```

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

> **Note:** If you used `./install.sh`, global hooks are already installed.
>
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

```text
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

1. Ensure you ran `./install.sh`, `copilot-command-ring setup` (global), or `copilot-command-ring deploy <path>` (per-repo).
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
| `COPILOT_RING_PORT` | Auto-detect | Set to `/dev/ttyACM1` or another device path if auto-detect selects the wrong device |
| `COPILOT_RING_BAUD` | `115200` | Serial baud rate; CircuitPython's USB CDC data channel is speed-independent |
| `COPILOT_RING_BRIGHTNESS` | `0.04` | LED brightness from `0.0` to `1.0` |
| `COPILOT_RING_PIXEL_COUNT` | `24` | Active LED count |
| `COPILOT_RING_LOG_LEVEL` | `WARNING` | Use `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `COPILOT_RING_DRY_RUN` | `false` | Set to `1`, `true`, or `yes` to skip serial sends |
| `COPILOT_RING_LOCK_TIMEOUT` | `1.0` | Seconds to wait for the multi-session serial lock |
| `COPILOT_HOME` | `~/.copilot` | Optional Copilot CLI home override; global setup installs hooks under `$COPILOT_HOME/hooks` |
