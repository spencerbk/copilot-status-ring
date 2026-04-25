# MicroPython Firmware

MicroPython firmware for the Copilot Command Ring.

## Requirements

- MicroPython 1.24 or later (required for USB CDC device support)
- `neopixel` built-in module (included in standard MicroPython firmware)
- `usb-device-cdc` package from micropython-lib (for dedicated serial channel on native-USB boards)

## Board Support

| Board | Support | Notes |
|-------|---------|-------|
| **Raspberry Pi Pico / Pico W** (RP2040) | ✅ Full | Native USB, dedicated CDC data channel, auto-detected on GPIO 6 |
| **Raspberry Pi Pico 2** (RP2350) | ✅ Full | Native USB, dedicated CDC data channel, auto-detected on GPIO 6 |
| **ESP32-S2** (Adafruit QT Py, Feather, etc.) | ✅ Full | Native USB, dedicated CDC data channel; set `NEOPIXEL_PIN` manually |
| **ESP32-S3** (Adafruit QT Py, Feather, etc.) | ✅ Full | Native USB, dedicated CDC data channel; set `NEOPIXEL_PIN` manually |
| **ESP32-C3** | ⚠️ Degraded | USB Serial/JTAG only — no custom CDC. Falls back to `sys.stdin` (shared with REPL); set `NEOPIXEL_PIN` manually. REPL noise may cause brief visual glitches. |
| **ESP32-C6** | ⚠️ Degraded | Same as ESP32-C3; set `NEOPIXEL_PIN` manually. |
| **ESP8266** | ❌ Unsupported | No USB device hardware. |

## Setup

1. Flash MicroPython firmware onto your board from [micropython.org/download](https://micropython.org/download/).
2. Install the USB CDC package:
   ```
   mpremote mip install usb-device-cdc
   ```
3. Copy files to the board:
   ```
   mpremote cp boot.py :boot.py
   mpremote cp ring_cdc.py :ring_cdc.py
   mpremote cp main.py :main.py
   mpremote cp neopixel_compat.py :neopixel_compat.py
   ```
4. If your board does not wire the ring to GPIO 6 by default (for example QT Py RP2040 or ESP32 variants), edit `NEOPIXEL_PIN` in `main.py` before resetting.
5. Reset the board (unplug and replug USB, or `mpremote reset`)

## Files

- `boot.py` — Sets up a second USB CDC endpoint for host communication (runs before main.py)
- `ring_cdc.py` — Shared module for passing the CDC reference from boot.py to main.py
- `main.py` — Main firmware with state machine, animations, multi-session tracking, and runtime `brightness`/`pixel_count` updates from host messages
- `neopixel_compat.py` — Thin compatibility wrapper adding brightness control to MicroPython's built-in neopixel

## Pin Configuration

The firmware auto-detects the NeoPixel data pin only on RP2040/RP2350 boards that use GPIO 6 by default. Other boards need a manual `NEOPIXEL_PIN` override.

| Board family | Pin | Notes |
|-------------|-----|-------|
| RP2040 / RP2350 boards wired to GPIO 6 | `Pin(6)` | Auto-detected via `sys.platform == "rp2"` |
| Other boards (QT Py RP2040, ESP32-S2/S3/C3/C6, custom wiring) | Set manually | Edit `NEOPIXEL_PIN` to the GPIO number for the pin you wired |

To override: edit `NEOPIXEL_PIN` at the top of `main.py`:

```python
NEOPIXEL_PIN = 18  # example: use your board's GPIO number
```

## Differences from CircuitPython

- Uses `micropython-lib`'s `usb-device-cdc` instead of built-in `usb_cdc`
- Software brightness scaling (CircuitPython's neopixel has hardware brightness)
- Runtime brightness and pixel-count config is applied after the first host message arrives; the startup wipe uses the firmware defaults
- Pin auto-detection is limited to RP2040/RP2350 boards wired to GPIO 6; other boards require a manual `NEOPIXEL_PIN` override
- Time tracking uses `time.ticks_ms()` with wraparound-safe `ticks_diff()` instead of `time.monotonic()`
- Watchdog via `machine.WDT` (one-way, cannot be stopped once started)
- ESP32-C3/C6 operate in degraded mode (shared REPL channel)

## Degraded Mode (ESP32-C3/C6)

These boards use `sys.stdin` because they do not support creating a custom USB CDC data channel. The firmware's JSON-line parser discards malformed input lines, so incidental REPL output is handled gracefully. If you interact with the REPL while the firmware is running, you may still see brief visual glitches on the ring because the REPL and host messages share the same input stream.
