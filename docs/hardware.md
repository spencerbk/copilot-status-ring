# Hardware Setup

This guide covers wiring, parts, and power for the Copilot Command Ring.

## Contents

- [Parts list](#parts-list)
- [Wiring diagram](#wiring-diagram)
- [Recommended boards](#recommended-boards)
- [Wire gauge](#wire-gauge)
- [Power notes](#power-notes)
- [Level shifting](#level-shifting)
- [Safety notes](#safety-notes)

---

## Parts list

| Part | Description | Notes |
|------|-------------|-------|
| **Adafruit NeoPixel Ring 24** | 24 × WS2812B RGB LEDs ([product 1586](https://www.adafruit.com/product/1586)) | The ring this project is designed for |
| **USB microcontroller** | RP2040, ESP32-S2/S3, or similar | Must support CircuitPython, MicroPython, and/or Arduino |
| **330 Ω resistor** (300–500 Ω) *(optional)* | In series with the NeoPixel data line | Recommended for permanent builds; safe to skip for short-wire prototyping |
| **1000 µF capacitor** (500–1000 µF) | Across 5V and GND near the ring | Protects LEDs against power-on inrush current |
| **74AHCT125 level shifter** *(optional)* | Shifts 3.3V data to 5V logic | Recommended for reliable signaling; see [Level shifting](#level-shifting) |
| **USB data cable** | Must be a **data** cable, not charge-only | Used for serial communication with the host |
| **Hookup wire / jumpers** | For connections between MCU, ring, and power | 22–24 AWG; breadboard jumpers or Dupont wires work for prototyping |

---

## Wiring diagram

The MCU plugs into your computer via USB and provides both power and data to the ring. Three wires run from the MCU to the NeoPixel ring:

```
         USB cable
Computer ════════════ MCU
                       ├─ D6  ──[330Ω*]──▶ Ring DIN
                       ├─ 5V  ───────────▶ Ring 5V
                       └─ GND ───────────▶ Ring GND
                                    ┌─[1000µF]─┐
                                   5V         GND
                                   (at the ring)
```

**Connections summary:**

1. **Data:** MCU data pin (e.g. GP6 on Pico, D6 on Feather/XIAO) → Ring DIN (optionally through a 330 Ω resistor)
2. **Power:** MCU 5V (VBUS) → Ring 5V
3. **Ground:** MCU GND → Ring GND
4. **Capacitor:** 1000 µF electrolytic across Ring 5V and Ring GND, as close to the ring as possible

> **\*** The 330 Ω resistor is optional for prototyping with short wires (< 15 cm). It protects the first LED against signal reflections and voltage spikes. Adafruit recommends it for permanent builds or longer wire runs.
>
> **Note:** For high-brightness or external power setups, see [Power notes](#power-notes).

---

## Recommended boards

Any board that supports CircuitPython, MicroPython, and/or Arduino with native USB will work. Good choices:

| Board | Runtime | Notes |
|-------|---------|-------|
| **Raspberry Pi Pico / Pico W** | CircuitPython + MicroPython + Arduino | RP2040-based, widely available, cheap |
| **Adafruit Feather RP2040** | CircuitPython + MicroPython + Arduino | Built-in LiPo charging, Feather ecosystem |
| **Adafruit QT Py RP2040** | CircuitPython + MicroPython + Arduino | Tiny form factor, STEMMA QT connector; MicroPython requires a manual `NEOPIXEL_PIN` override |
| **Adafruit Feather ESP32-S2** | CircuitPython + MicroPython + Arduino | Wi-Fi capable (not needed for v1, but nice to have); MicroPython requires a manual `NEOPIXEL_PIN` override |
| **Adafruit Feather ESP32-S3** | CircuitPython + MicroPython + Arduino | Wi-Fi + BLE, native USB; MicroPython requires a manual `NEOPIXEL_PIN` override |
| **Adafruit QT Py ESP32-S2** | CircuitPython + MicroPython + Arduino | Tiny form factor, STEMMA QT; MicroPython requires a manual `NEOPIXEL_PIN` override |
| **Adafruit QT Py ESP32-S3** | CircuitPython + MicroPython + Arduino | Tiny form factor, Wi-Fi + BLE; MicroPython requires a manual `NEOPIXEL_PIN` override |
| **Seeed Studio XIAO RP2350** | CircuitPython + MicroPython | RP2350 dual-core, ultra-compact; default `D6` pin works |
| **Seeed Studio XIAO ESP32-C6** | CircuitPython + MicroPython + Arduino | Wi-Fi 6 + BLE 5, ultra-compact; MicroPython runs in degraded mode and requires a manual `NEOPIXEL_PIN` override |

The firmware does **not** hard-code a specific board. CircuitPython auto-detects the correct NeoPixel data pin at startup. MicroPython auto-detects RP2040/RP2350-family boards that wire the ring to GPIO 6; other boards require a manual `NEOPIXEL_PIN` override. Pin count is configurable.

### Pin configuration by board

The CircuitPython firmware auto-detects the NeoPixel data pin using `board.board_id`. The MicroPython firmware auto-detects only RP2040/RP2350-family boards that use GPIO 6 by default; other boards require a manual `NEOPIXEL_PIN` override. For Arduino, edit `NEOPIXEL_PIN` in the `.ino` sketch.

| Board | CircuitPython pin (auto-detected) | MicroPython pin | Arduino pin | Notes |
|-------|----------------------------------|-----------------|-------------|-------|
| Raspberry Pi Pico | `board.GP6` | `Pin(6)` | `6` | Auto-detected |
| Adafruit Feather RP2040 | `board.D6` | `Pin(6)` | `6` | Auto-detected |
| Adafruit QT Py RP2040 | `board.A0` | Set manually | `A0` | MicroPython requires a manual override; use the GPIO number for the pin you wired |
| Adafruit Feather ESP32-S2 | `board.D6` | Set manually | `6` | MicroPython requires a manual override |
| Adafruit Feather ESP32-S3 | `board.D6` | Set manually | `6` | MicroPython requires a manual override |
| Adafruit QT Py ESP32-S2 | `board.A0` | Set manually | `A0` | MicroPython requires a manual override |
| Adafruit QT Py ESP32-S3 | `board.A0` | Set manually | `A0` | MicroPython requires a manual override |
| Seeed Studio XIAO RP2350 | `board.D6` | `Pin(6)` | — | Auto-detected; Arduino not yet supported |
| Seeed Studio XIAO ESP32-C6 | `board.D6` | Set manually | `6` | MicroPython requires a manual override and runs in degraded mode |

To override CircuitPython auto-detection, edit `NEOPIXEL_PIN` at the top of `code.py`:
```python
NEOPIXEL_PIN = board.A0  # override auto-detection
```

For Arduino, edit `NEOPIXEL_PIN` in the `.ino` sketch:
```cpp
#define NEOPIXEL_PIN A0  // QT Py boards
```

For MicroPython, edit `NEOPIXEL_PIN` at the top of `main.py`:
```python
NEOPIXEL_PIN = 18  # example: use the GPIO number for your board's data pin
```

---

## Wire gauge

| Connection | Recommended gauge | Notes |
|------------|-------------------|-------|
| **Data (MCU data pin → Ring DIN)** | 22–26 AWG | Low current signal line; e.g. GP6 on Pico, D6 on Feather/XIAO ESP32 |
| **Power (5V → Ring 5V)** | 22–24 AWG | Adequate for the ring at low brightness (4–10%) |
| **Ground (GND → Ring GND)** | 22–24 AWG | Match the power wire gauge |

Standard breadboard jumper wires and Dupont wires (typically 22–24 AWG) are fine for prototyping. For a permanent soldered build, 22 AWG solid-core is a good all-around choice.

> **Note:** Wire gauge matters more at high brightness or long runs (> 30 cm), where voltage drop on thinner wires can cause color issues on far-end LEDs. For those cases, use 20 AWG or heavier on the power and ground lines.

---

## Power notes

The NeoPixel Ring 24 can draw up to **~1.4 A at full white, full brightness** (24 pixels × ~60 mA each). In practice, the Copilot Command Ring runs at very low brightness (4–10%), so current draw is much lower.

**Rules of thumb:**

- **≤ 8 pixels at moderate brightness:** Safe to power directly from the MCU's USB 5V pin.
- **Full ring at low brightness (≤ 10%):** Usually fine from MCU USB, but monitor for voltage droop.
- **Full ring at high brightness:** Use an **external 5V power supply** connected directly to the ring. Do not run >500 mA through the MCU's voltage regulator.

> **Warning:** If powering the ring from an external supply, the MCU and the supply **must share a common ground**. Connect GND before connecting 5V.

---

## Level shifting

NeoPixels expect a **5V logic level** on the data line. Most modern MCUs (RP2040, ESP32) output **3.3V logic**. This often works, but is technically out of spec and can cause flickering or missed data on longer wires.

**When you need a level shifter:**

- Wire between MCU and ring is longer than ~15 cm
- You see occasional flickering or color glitches
- You want rock-solid reliability

**Recommended part:** 74AHCT125 quad level shifter

**Wiring with level shifter:**

```
MCU D6  ──────────▶ 74AHCT125 Input (1A)
                    74AHCT125 Output (1Y) ──[330Ω]──▶ Ring DIN
MCU 5V  ──────────▶ 74AHCT125 VCC ──────────────────▶ Ring 5V
MCU GND ──────────▶ 74AHCT125 GND ──────────────────▶ Ring GND
                    74AHCT125 OE (1OE) ──▶ GND (always enabled)
```

If you're using short wires (< 10 cm) and low pixel counts, you can skip the level shifter for prototyping. Add it if you see signal issues.

---

## Safety notes

1. **Connect GND first.** When wiring or plugging in, always connect the ground wire before power or data. Disconnect in reverse order.
2. **The capacitor protects against inrush current.** The 1000 µF capacitor absorbs the initial surge when power is applied. Without it, you risk damaging the first LED in the chain.
3. **The resistor protects the data line.** The 330 Ω resistor prevents signal reflections and voltage spikes from reaching the first LED's data input. It's optional for short-wire prototyping but recommended for permanent builds.
4. **Don't exceed the MCU's current capacity.** If the ring is drawing more than ~500 mA, use an external power supply.
5. **Check capacitor polarity.** Electrolytic capacitors are polarized — the longer leg (or the side without the stripe) goes to 5V, the shorter leg (striped side) goes to GND.
6. **Use a data-capable USB cable.** Charge-only cables lack the D+/D− wires needed for serial communication. If your board shows up as a drive but not a serial port, try a different cable.
