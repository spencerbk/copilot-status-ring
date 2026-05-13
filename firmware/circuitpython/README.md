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
- `code.py` — Main firmware with state machine and animations. Tracks multiple concurrent Copilot CLI sessions and displays the highest-priority state across all of them. Stale sessions (no messages for 5 minutes) are pruned; once every session is pruned or a session ends, the ring follows `idle_mode`: dim breathing by default, or fully off when `idle_mode` is `"off"`. Runtime `brightness` and `pixel_count` values from host messages are applied after receipt. For long-running sessions on small boards such as the Pico, it drains queued JSON-line serial input each loop, reads buffered data regardless of USB connection state (so messages are never lost between rapid hook invocations), clears stale partial input only on USB reconnect, runs garbage collection after serial parsing work, and uses watchdog/reload recovery when supported.

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

## Ring size

The 24-LED Adafruit NeoPixel Ring (product 1586) is the default, but the 16-LED ring (product 1463) and the 12-LED ring (product 1643) are first-class targets too. The host bridge sends `pixel_count` to the firmware in every message and the firmware applies it at runtime — animations (including the working spinner) auto-scale to the ring you wired.

The simplest way to set the value is the `setup-status-ring` wizard, which prompts for 24 / 16 / 12 and writes the choice into `.copilot-command-ring.local.json`. You can also set `pixel_count` directly in that file or `COPILOT_RING_PIXEL_COUNT` in the environment.

`NUM_PIXELS = 24` at the top of `code.py` is the *startup* default used only for the boot wipe before the first host message arrives. For a perfectly clean wipe on a 16- or 12-LED ring, edit it to match before flashing.
