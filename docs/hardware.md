# Hardware Setup

This guide covers wiring, parts, and power for the Copilot Command Ring.

---

## Parts list

| Part | Description | Notes |
|------|-------------|-------|
| **Adafruit NeoPixel Ring 24** | 24 × WS2812B RGB LEDs ([product 1586](https://www.adafruit.com/product/1586)) | The ring this project is designed for |
| **USB microcontroller** | RP2040, ESP32-S2/S3, or similar | Must support CircuitPython and/or Arduino |
| **330 Ω resistor** (300–500 Ω) | In series with the NeoPixel data line | Prevents signal reflections; place close to ring DIN |
| **1000 µF capacitor** (500–1000 µF) | Across 5V and GND near the ring | Protects LEDs against power-on inrush current |
| **74AHCT125 level shifter** *(optional)* | Shifts 3.3V data to 5V logic | Recommended for reliable signaling; see [Level shifting](#level-shifting) |
| **USB data cable** | Must be a **data** cable, not charge-only | Used for serial communication with the host |
| **Hookup wire / jumpers** | For connections between MCU, ring, and power | Solid-core or silicone-stranded |

---

## Wiring diagram

```
MCU D6 ──[330Ω]──> Ring DIN
5V Power ──────────> Ring 5V
GND ─────────────── Ring GND ─── MCU GND
             ┌─[1000µF]─┐
             5V        GND
```

**Connections summary:**

1. **Data:** MCU data pin (e.g. D6) → 330 Ω resistor → Ring DIN
2. **Power:** 5V supply → Ring 5V
3. **Ground:** Ring GND, MCU GND, and power supply GND must all share a common ground
4. **Capacitor:** 1000 µF electrolytic across the 5V and GND rails, as close to the ring as possible

> **Tip:** The resistor goes on the data line, the capacitor goes on the power rail. Don't mix them up.

---

## Recommended boards

Any board that supports CircuitPython and/or Arduino with native USB will work. Good choices:

| Board | Runtime | Notes |
|-------|---------|-------|
| **Raspberry Pi Pico / Pico W** | CircuitPython + Arduino | RP2040-based, widely available, cheap |
| **Adafruit Feather RP2040** | CircuitPython + Arduino | Built-in LiPo charging, Feather ecosystem |
| **Adafruit QT Py RP2040** | CircuitPython + Arduino | Tiny form factor, STEMMA QT connector |
| **Adafruit Feather ESP32-S2** | CircuitPython + Arduino | Wi-Fi capable (not needed for v1, but nice to have) |
| **Adafruit Feather ESP32-S3** | CircuitPython + Arduino | Wi-Fi + BLE, native USB |
| **Adafruit QT Py ESP32-S2** | CircuitPython + Arduino | Tiny form factor, STEMMA QT; **use `A0` for data pin** |
| **Adafruit QT Py ESP32-S3** | CircuitPython + Arduino | Tiny form factor, Wi-Fi + BLE; **use `A0` for data pin** |
| **Seeed Studio XIAO RP2350** | CircuitPython | RP2350 dual-core, ultra-compact; default `D6` pin works |
| **Seeed Studio XIAO ESP32-C6** | CircuitPython + Arduino | Wi-Fi 6 + BLE 5, ultra-compact; default `D6` pin works |

The firmware does **not** hard-code a specific board. Pin assignments and pixel count are configurable.

### Pin configuration by board

The firmware defaults to `board.D6` (CircuitPython) / pin `6` (Arduino). Some boards use different pin names:

| Board | CircuitPython pin | Arduino pin | Notes |
|-------|------------------|-------------|-------|
| Raspberry Pi Pico | `board.GP6` | `6` | Change pin to `board.GP6` |
| Adafruit Feather RP2040 | `board.D6` | `6` | Default works |
| Adafruit QT Py RP2040 | `board.A0` | `A0` | No D6 on QT Py boards |
| Adafruit QT Py ESP32-S2 | `board.A0` | `A0` | No D6; use any available GPIO |
| Adafruit QT Py ESP32-S3 | `board.A0` | `A0` | No D6; use any available GPIO |
| Seeed Studio XIAO RP2350 | `board.D6` | — | Default works; Arduino not yet supported |
| Seeed Studio XIAO ESP32-C6 | `board.D6` | `6` | Default works |

To change the pin in CircuitPython, edit `NEOPIXEL_PIN` at the top of `code.py`:
```python
NEOPIXEL_PIN = board.A0  # QT Py boards
```

For Arduino, edit `NEOPIXEL_PIN` in the `.ino` sketch:
```cpp
#define NEOPIXEL_PIN A0  // QT Py boards
```

---

## Power notes

The NeoPixel Ring 24 can draw up to **~1.4 A at full white, full brightness** (24 pixels × ~60 mA each). In practice, the Copilot Command Ring runs at very low brightness (6–10%), so current draw is much lower.

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
MCU D6 ──> 74AHCT125 Input (1A)
           74AHCT125 Output (1Y) ──[330Ω]──> Ring DIN
           74AHCT125 VCC ──> 5V
           74AHCT125 GND ──> GND
           74AHCT125 OE (1OE) ──> GND (always enabled)
```

If you're using short wires (< 10 cm) and low pixel counts, you can skip the level shifter for prototyping. Add it if you see signal issues.

---

## Safety notes

1. **Connect GND first.** When wiring or plugging in, always connect the ground wire before power or data. Disconnect in reverse order.
2. **The capacitor protects against inrush current.** The 1000 µF capacitor absorbs the initial surge when power is applied. Without it, you risk damaging the first LED in the chain.
3. **The resistor protects the data line.** The 330 Ω resistor prevents signal reflections and voltage spikes from reaching the first LED's data input.
4. **Don't exceed the MCU's current capacity.** If the ring is drawing more than ~500 mA, use an external power supply.
5. **Check capacitor polarity.** Electrolytic capacitors are polarized — the longer leg (or the side without the stripe) goes to 5V, the shorter leg (striped side) goes to GND.
6. **Use a data-capable USB cable.** Charge-only cables lack the D+/D− wires needed for serial communication. If your board shows up as a drive but not a serial port, try a different cable.
