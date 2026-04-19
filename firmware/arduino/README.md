# Arduino Firmware

Arduino firmware for the Copilot Command Ring.

## Requirements

- Arduino IDE or CLI
- Adafruit NeoPixel library (`Adafruit_NeoPixel`)
- Optionally ArduinoJson library for JSON parsing
- USB-capable Arduino board (e.g., Arduino Uno, Nano, or RP2040-based)

## Setup

1. Open `copilot_command_ring.ino` in the Arduino IDE.
2. Install the **Adafruit NeoPixel** library via Library Manager.
3. Select your board and port.
4. Upload the sketch.

## Configuration

Edit the `#define` values at the top of the sketch:
- `NEOPIXEL_PIN` — data pin connected to the ring
- `PIXEL_COUNT` — number of LEDs (24 for the standard ring)
- `BRIGHTNESS` — LED brightness (0–255)

## Board-specific notes

Most boards use pin `6` for `NEOPIXEL_PIN`. Exceptions:

- **QT Py boards (RP2040, ESP32-S2, ESP32-S3):** Use `A0` instead — these boards have no pin 6. Set `#define NEOPIXEL_PIN A0`.
- **Seeed Studio XIAO ESP32-C6:** Pin `6` works (default).
- **Seeed Studio XIAO RP2350:** Arduino support is not yet available; use CircuitPython instead.
