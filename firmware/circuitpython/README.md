# CircuitPython Firmware

CircuitPython firmware for the Copilot Command Ring.

## Requirements

- CircuitPython 10.x board with native USB
- `neopixel` library from the Adafruit CircuitPython Bundle

## Setup

1. Install CircuitPython on your board.
2. Copy `neopixel.mpy` from the Adafruit Bundle to `CIRCUITPY/lib/`.
3. Copy `boot.py` and `code.py` to the root of the `CIRCUITPY` drive.
4. Restart the board.

## Files

- `boot.py` — Sets custom USB product name ("Copilot Command Ring") and enables `usb_cdc.data` for host communication.
- `code.py` — Main firmware with state machine and animations. Tracks multiple concurrent Copilot CLI sessions and displays the highest-priority state across all of them. Includes two-tier stale-idle behavior: sessions with no messages for 5 minutes are pruned, and if all sessions are stale the ring shows a dim breathing animation for up to 1 hour before going fully dark. For long-running sessions on small boards such as the Pico, it drains queued JSON-line serial input each loop, reads buffered data regardless of USB connection state (so messages are never lost between rapid hook invocations), clears stale partial input only on USB reconnect, runs garbage collection after serial parsing work, and uses watchdog/reload recovery when supported.

## Pin configuration

The firmware auto-detects the NeoPixel data pin based on your board:

| Board | Auto-detected pin |
|-------|------------------|
| Raspberry Pi Pico / Pico W | `board.GP6` |
| Adafruit Feather RP2040 | `board.D6` |
| Adafruit QT Py RP2040 / ESP32-S2 / ESP32-S3 | `board.A0` |
| Seeed Studio XIAO RP2350 / ESP32-C6 | `board.D6` |

To override auto-detection, edit `NEOPIXEL_PIN` at the top of `code.py`:
```python
NEOPIXEL_PIN = board.A0  # override auto-detection
```
