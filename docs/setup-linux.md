# Setup — Linux

Step-by-step guide to set up the Copilot Command Ring on Linux.

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

## 2. Install pyserial

```bash
pip3 install pyserial
```

Or use your system package manager:

```bash
# Debian/Ubuntu
sudo apt install python3-serial

# Fedora
sudo dnf install python3-pyserial

# Arch
sudo pacman -S python-pyserial
```

Verify:

```bash
python3 -c "import serial; print(serial.VERSION)"
```

---

## 3. Find your serial device

Connect your microcontroller via USB, then list serial devices:

```bash
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

You should see something like:

```
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
> ```bash
> sudo usermod -aG uucp $USER
> ```

---

## 5. Configure the serial port

**Option A — environment variable:**

```bash
export COPILOT_RING_PORT="/dev/ttyACM1"
```

Add it to your shell profile (`~/.bashrc` or `~/.zshrc`) to make it permanent:

```bash
echo 'export COPILOT_RING_PORT="/dev/ttyACM1"' >> ~/.bashrc
```

**Option B — config file:**

Create `.copilot-command-ring.local.json` in your project root:

```json
{
  "serial_port": "/dev/ttyACM1",
  "brightness": 0.08
}
```

**Option C — auto-detect:**

If you don't set a port, the host bridge will try to auto-detect your board by scanning serial devices.

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
   cp firmware/circuitpython/boot.py /media/$USER/CIRCUITPY/boot.py
   cp firmware/circuitpython/code.py /media/$USER/CIRCUITPY/code.py
   cp -r firmware/circuitpython/lib/* /media/$USER/CIRCUITPY/lib/
   sync
   ```
7. The board reboots automatically.

> **Note:** After copying `boot.py`, unplug and replug the board so the USB CDC data channel activates.

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
| `COPILOT_RING_PORT` | Serial port | `/dev/ttyACM1` |
| `COPILOT_RING_BAUD` | Baud rate (Arduino only) | `115200` |
| `COPILOT_RING_BRIGHTNESS` | LED brightness (0.0–1.0) | `0.08` |
| `COPILOT_RING_LOG_LEVEL` | Log verbosity | `DEBUG` |
| `COPILOT_RING_DRY_RUN` | Skip serial send | `1` |
