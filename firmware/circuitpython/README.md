# CircuitPython Firmware

CircuitPython firmware for the Copilot Command Ring.

## Requirements

- CircuitPython 9.x+ board with native USB
- `neopixel` library from the Adafruit CircuitPython Bundle

## Setup

1. Install CircuitPython on your board.
2. Copy `neopixel.mpy` from the Adafruit Bundle to `CIRCUITPY/lib/`.
3. Copy `boot.py` and `code.py` to the root of the `CIRCUITPY` drive.
4. Restart the board.

## Files

- `boot.py` — Enables `usb_cdc.data` for host communication.
- `code.py` — Main firmware with state machine and animations.

## Pin configuration

The firmware defaults to `board.D6` for the NeoPixel data line. Some boards expose different pin names:

| Board | Pin to use |
|-------|-----------|
| Raspberry Pi Pico | `board.GP6` — change from default `D6` |
| Adafruit Feather RP2040 | `board.D6` (default works) |
| Adafruit QT Py RP2040 / ESP32-S2 / ESP32-S3 | `board.A0` — **no `D6` on QT Py boards** |
| Seeed Studio XIAO RP2350 / ESP32-C6 | `board.D6` (default works) |

To change the pin, edit `NEOPIXEL_PIN` at the top of `code.py`:
```python
NEOPIXEL_PIN = board.A0  # QT Py boards
```
