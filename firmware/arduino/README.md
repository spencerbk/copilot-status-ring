# Arduino Firmware

Arduino firmware for the Copilot Command Ring — full feature parity with
the CircuitPython and MicroPython variants.

## Features

- **Multi-session tracking**: Up to 8 concurrent Copilot CLI sessions with
  priority-based arbitration (highest-urgency session wins the ring).
- **TTL decay**: Sessions past their TTL fade to `agent_idle` breathing.
- **Stale pruning**: Sessions with no messages for 5 minutes are removed.
- **Idle mode**: Configurable `breathing` (default) or `off` when no sessions
  are active.
- **Transient overlay**: Flash notifications (tool_ok, tool_error, tool_denied,
  error, notify) overlay the persistent state and revert automatically.
- **Brightness boost**: Dim states (agent_idle) get extra brightness for
  visibility.
- **Runtime display config**: Host-sent `brightness` and `pixel_count` update
  the active NeoPixel settings after messages arrive.
- **Startup animation**: Magenta wipe confirms the ring is alive on boot.
- **Watchdog / error recovery**: Hardware watchdog on RP2040, serial silence
  timeout (10 min), and consecutive parse-error limit trigger a software reset.
- **Dual JSON parser**: ArduinoJson (compile with `-DUSE_ARDUINOJSON`) or a
  zero-dependency strstr-based extractor (default).

## Requirements

- Arduino IDE or CLI
- Adafruit NeoPixel library (`Adafruit_NeoPixel`)
- Optionally ArduinoJson v7 library for JSON parsing
- USB-capable board: RP2040-based (Pico, Feather RP2040, QT Py RP2040) or
  ESP32-S2/S3/C6

## Setup

1. Open `copilot_command_ring.ino` in the Arduino IDE.
2. Install the **Adafruit NeoPixel** library via Library Manager.
3. Select your board and port.
4. Upload the sketch.

## Configuration

Edit the `#define` values at the top of the sketch:

| Define | Default | Description |
|--------|---------|-------------|
| `NEOPIXEL_PIN` | `6` | Data pin connected to the ring |
| `PIXEL_COUNT` | `24` | Number of LEDs |
| `BRIGHTNESS` | `10` | Base LED brightness (0–255) |
| `BRIGHTNESS_BOOST` | `5` | Extra brightness for dim states |
| `MAX_SESSIONS` | `8` | Max concurrent sessions tracked |
| `STALE_TIMEOUT_MS` | `300000` | Prune sessions after 5 min silence |
| `SERIAL_SILENCE_MS` | `600000` | Reset after 10 min with no serial data |

The host can override `BRIGHTNESS` and `PIXEL_COUNT` at runtime with
`COPILOT_RING_BRIGHTNESS`, `COPILOT_RING_PIXEL_COUNT`, or the local JSON config.
The startup wipe uses the sketch defaults until the first host message arrives.

## Board-specific notes

Most boards use pin `6` for `NEOPIXEL_PIN`. Exceptions:

- **QT Py boards (RP2040, ESP32-S2, ESP32-S3):** Use `A0` instead — these
  boards have no pin 6. Set `#define NEOPIXEL_PIN A0`.
- **Seeed Studio XIAO ESP32-C6:** Pin `6` works (default).
- **Seeed Studio XIAO RP2350:** Arduino support is not yet available; use
  CircuitPython instead.

## Platform support

| Platform | Watchdog | Software reset |
|----------|----------|----------------|
| RP2040 | ✅ Hardware (8 s) | `watchdog_reboot()` |
| ESP32 | ❌ Skipped | `ESP.restart()` |
| Other | ❌ Skipped | Infinite loop (hang) |

## JSON parser selection

By default, the firmware uses a lightweight `strstr`-based JSON extractor that
requires no external dependencies. To use ArduinoJson v7 instead, add
`-DUSE_ARDUINOJSON` to your build flags or add `#define USE_ARDUINOJSON` before
the `#include <ArduinoJson.h>` line.
