# Hardware Setup

This guide covers wiring, parts, and power for the Copilot Command Ring. The 24-LED ring (Adafruit product 1586) and the 16-LED ring (Adafruit product 1463) are both first-class targets — the firmware auto-scales the spinner segment to match the ring size, and the setup wizard prompts you to pick during install. For a first build, keep the default low brightness and power either ring from the board's USB 5V/VBUS pin; move to an external 5V supply only if you increase brightness, use more pixels, or see voltage-drop symptoms.

## Contents

- [Parts list](#parts-list)
- [Recommended first build](#recommended-first-build)
- [Ring size selection](#ring-size-selection)
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
| **Adafruit NeoPixel Ring 24** | 24 × WS2812B RGB LEDs ([product 1586](https://www.adafruit.com/product/1586)) | Project default; widest visual presence |
| **Adafruit NeoPixel Ring 16** | 16 × WS2812B RGB LEDs ([product 1463](https://www.adafruit.com/product/1463)) | Smaller form factor; lower current draw — also a first-class target |
| **Adafruit NeoPixel Ring 12** | 12 × WS2812B RGB LEDs ([product 1643](https://www.adafruit.com/product/1643)) | Smallest supported ring; offered in the setup wizard |
| **USB microcontroller** | RP2040, ESP32-S2/S3, or similar | Must support CircuitPython, MicroPython, and/or Arduino |
| **330 Ω resistor** (300–500 Ω) *(optional)* | In series with the NeoPixel data line | Recommended for permanent builds; safe to skip for short-wire prototyping |
| **1000 µF capacitor** (500–1000 µF) | Across 5V and GND near the ring | Protects LEDs against power-on inrush current |
| **74AHCT125 level shifter** *(optional)* | Shifts 3.3V data to 5V logic | Recommended for reliable signaling; see [Level shifting](#level-shifting) |
| **USB data cable** | Must be a **data** cable, not charge-only | Used for serial communication with the host |
| **Hookup wire / jumpers** | For connections between MCU, ring, and power | 22–24 AWG; breadboard jumpers or Dupont wires work for prototyping |

---

## Recommended first build

Either the 24-LED ring or the 16-LED ring is a great starting point. Pick whichever you have on hand:

| Choice | 24-LED build | 16-LED build |
|--------|--------------|--------------|
| LED device | Adafruit NeoPixel Ring 24 (product 1586) | Adafruit NeoPixel Ring 16 (product 1463) |
| Firmware | CircuitPython | CircuitPython |
| Power | Board USB 5V/VBUS to ring 5V | Board USB 5V/VBUS to ring 5V |
| Data | Board-specific data pin (`D6`/`GP6` on Pico/Feather-style boards) to ring `DIN` through a 330 Ω resistor | Same wiring as the 24-LED build |
| Ground | Board GND to ring GND | Board GND to ring GND |
| Protection | 1000 µF capacitor across ring 5V/GND | 1000 µF capacitor across ring 5V/GND |
| `pixel_count` | `24` (default) | `16` (set during `setup-status-ring`) |

Both work well at the default low brightness. Add a 74AHCT125 level shifter if the data wire is longer than about 15 cm, the ring flickers, or the build is permanent.

---

## Ring size selection

The host bridge sends `pixel_count` in every message, and all three firmware variants apply it at runtime — so a single firmware build supports any ring size you wire up. The setup wizard (`setup-status-ring`) prompts you to pick from 24, 16, or 12 LEDs and writes your choice into `~/.copilot-command-ring.local.json` (global scope) or `<repo>/.copilot-command-ring.local.json` (per-repo scope).

You can also override outside the wizard by setting `COPILOT_RING_PIXEL_COUNT` or editing the `pixel_count` field in your local JSON config. The spinner segment auto-scales to ~25% of the ring (with a floor of 2 LEDs) at any size.

> **Startup wipe note:** The firmware-default `NUM_PIXELS` (CircuitPython, MicroPython) and `PIXEL_COUNT` (Arduino) is `24`. Until the first host message arrives after boot, the startup wipe assumes a 24-LED ring. On a 16- or 12-LED ring, the wipe still works — the firmware just writes a few extra bytes that vanish into the wire — but for a perfectly clean boot animation, edit `NUM_PIXELS` / `PIXEL_COUNT` in the firmware to match your ring before flashing.

---

## Wiring diagram

The MCU plugs into your computer via USB and provides both power and data to the ring. Three wires run from the MCU to the NeoPixel ring:

```text
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

NeoPixel current draw at full white, full brightness is approximately **60 mA per pixel**:

| Ring | Pixels | Max draw at full white / full brightness | Typical draw at default 4 % brightness |
|------|--------|-----------------------------------------|----------------------------------------|
| Ring 24 (product 1586) | 24 | ~1.4 A | ~60 mA |
| Ring 16 (product 1463) | 16 | ~0.96 A | ~40 mA |
| Ring 12 (product 1643) | 12 | ~0.72 A | ~30 mA |

In practice, the Copilot Command Ring runs at very low brightness (4–10%), so current draw is much lower than the theoretical max.

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

```text
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
