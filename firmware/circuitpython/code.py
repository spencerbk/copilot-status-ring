# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Copilot Command Ring — CircuitPython firmware.

State-machine-driven NeoPixel ring controller. Receives JSON Lines commands
over USB serial (usb_cdc.data) and renders animations on a 24-pixel ring.
"""

import gc
import json
import math
import time

import board  # type: ignore[reportMissingImports]
import neopixel  # type: ignore[reportMissingImports]
import usb_cdc  # type: ignore[reportMissingImports]

# ── Configuration ──────────────────────────────────────────────────────────
# Data pin for the NeoPixel ring — change to match your board:
#   Feather RP2040 / XIAO RP2350 / XIAO ESP32-C6: board.D6 (default)
#   Raspberry Pi Pico / Pico W:                    board.GP6
#   QT Py RP2040 / QT Py ESP32-S2 / QT Py ESP32-S3: board.A0
NEOPIXEL_PIN = board.GP6
NUM_PIXELS = 24
BRIGHTNESS = 0.04  # keep low to avoid blinding / power issues
BRIGHTNESS_BOOST = 0.02  # extra brightness for dim states (breathing)
PIXEL_ORDER = neopixel.GRB
SPINNER_WIDTH = 6  # number of LEDs in the spinner segment
LOOP_DELAY = 0.02  # ~50 fps
SERIAL_BUF_MAX = 512  # discard buffer if no newline within this many bytes

# ── Color palette ──────────────────────────────────────────────────────────
COLOR_OFF = (0, 0, 0)
COLOR_SESSION_START = (60, 60, 50)     # warm white
COLOR_PROMPT = (0, 152, 255)           # copilot blue (#0098FF)
COLOR_WORKING = (133, 52, 243)         # copilot purple (#8534F3)
COLOR_TOOL_OK = (15, 191, 62)          # github green (#0FBF3E)
COLOR_TOOL_ERROR = (218, 54, 51)       # primer danger (#DA3633)
COLOR_PERMISSION = (210, 153, 34)      # primer attention (#D29922)
COLOR_SUBAGENT = (200, 0, 160)         # magenta — distinct from working purple
COLOR_IDLE_DIM = (40, 40, 35)          # dim white
COLOR_COMPACTING = (0, 180, 180)       # cyan
COLOR_ERROR = (218, 54, 51)            # primer danger (#DA3633)
COLOR_NOTIFY = (200, 200, 200)         # white

# State → (animation_function_name, color, kwargs)
STATE_MAP = {
    "off":                 ("off",       COLOR_OFF,           {}),
    "idle":                ("off",       COLOR_OFF,           {}),
    "session_start":       ("wipe",      COLOR_SESSION_START, {"duration": 0.8}),
    "prompt_submitted":    ("wipe",      COLOR_PROMPT,        {"duration": 0.8}),
    "working":             (
        "spinner",
        COLOR_WORKING,
        {"width": SPINNER_WIDTH, "period": 1.0},
    ),
    "tool_ok":             ("flash",     COLOR_TOOL_OK,       {"duration": 0.3}),
    "tool_error":          ("flash",     COLOR_TOOL_ERROR,    {"duration": 0.3}),
    "awaiting_permission": ("blink",     COLOR_PERMISSION,    {"period": 0.6}),
    "subagent_active":     ("chase",     COLOR_SUBAGENT,      {"spacing": 4, "period": 1.0}),
    "agent_idle":          ("breathing", COLOR_IDLE_DIM,      {"period": 3.0}),
    "compacting":          ("wipe",      COLOR_COMPACTING,    {"duration": 0.8}),
    "error":               ("flash",     COLOR_ERROR,         {"duration": 0.8}),
    "notify":              ("flash",     COLOR_NOTIFY,        {"duration": 0.3}),
}

# States that auto-return to the previous state after their animation
TRANSIENT_STATES = {"tool_ok", "tool_error", "error", "notify"}

# States that get a brightness boost for visibility
BOOSTED_STATES = {"agent_idle"}


# ── Animation engine ───────────────────────────────────────────────────────

class StatusRing:
    """Drives a NeoPixel ring through named animation states."""

    def __init__(self, pixels, num_pixels):
        self.pixels = pixels
        self.num_pixels = num_pixels
        self.state = "off"
        self.prev_state = "off"
        self.state_start = 0.0
        self.step = 0

    def set_state(self, new_state):
        """Transition to *new_state*, recording the previous state."""
        if new_state not in STATE_MAP:
            new_state = "off"
        if new_state != self.state:
            self.prev_state = self.state
            self.state = new_state
            self.state_start = time.monotonic()
            self.step = 0
            # Boost brightness for dim states, restore for others
            if new_state in BOOSTED_STATES:
                self.pixels.brightness = BRIGHTNESS + BRIGHTNESS_BOOST
            elif self.prev_state in BOOSTED_STATES:
                self.pixels.brightness = BRIGHTNESS

    # ── tick dispatcher ────────────────────────────────────────────────

    def tick(self, now):
        """Call once per loop iteration with current monotonic time."""
        elapsed = now - self.state_start
        entry = STATE_MAP.get(self.state)
        if entry is None:
            self._anim_off()
            return

        anim_name, color, kwargs = entry

        # Dispatch to the matching _anim_* method
        if anim_name == "off":
            self._anim_off()
        elif anim_name == "flash":
            self._anim_flash(color, elapsed, kwargs.get("duration", 0.3))
        elif anim_name == "blink":
            self._anim_blink(color, elapsed, kwargs.get("period", 0.6))
        elif anim_name == "spinner":
            self._anim_spinner(color, elapsed, kwargs.get("width", SPINNER_WIDTH),
                               kwargs.get("period", 1.0))
        elif anim_name == "wipe":
            self._anim_wipe(color, elapsed, kwargs.get("duration", 0.8))
        elif anim_name == "chase":
            self._anim_chase(color, elapsed, kwargs.get("spacing", 4),
                             kwargs.get("period", 1.0))
        elif anim_name == "breathing":
            self._anim_breathing(color, elapsed, kwargs.get("period", 3.0))
        elif anim_name == "solid":
            self._anim_solid(color)
        else:
            self._anim_off()

        self.pixels.show()

    # ── helper: revert transient states ────────────────────────────────

    def _revert(self):
        """Return to the previous state (used by flash/transient anims)."""
        target = self.prev_state
        if target in TRANSIENT_STATES:
            target = "off"
        self.state = target
        self.state_start = time.monotonic()
        self.step = 0
        # Re-apply brightness boost if reverting to a boosted state
        if target in BOOSTED_STATES:
            self.pixels.brightness = BRIGHTNESS + BRIGHTNESS_BOOST

    # ── animation implementations ──────────────────────────────────────

    def _anim_off(self):
        self.pixels.fill(COLOR_OFF)

    def _anim_solid(self, color):
        self.pixels.fill(color)

    def _anim_flash(self, color, elapsed, duration):
        if elapsed < duration:
            self.pixels.fill(color)
        else:
            self._revert()

    def _anim_blink(self, color, elapsed, period):
        half = period / 2.0
        phase = elapsed % period
        if phase < half:
            self.pixels.fill(color)
        else:
            self.pixels.fill(COLOR_OFF)

    def _anim_spinner(self, color, elapsed, width, period):
        frac = (elapsed % period) / period
        head = int(frac * self.num_pixels) % self.num_pixels
        for i in range(self.num_pixels):
            # Light *width* pixels behind the head position
            dist = (head - i) % self.num_pixels
            if dist < width:
                self.pixels[i] = color
            else:
                self.pixels[i] = COLOR_OFF

    def _anim_wipe(self, color, elapsed, duration):
        frac = min(elapsed / duration, 1.0)
        lit = int(frac * self.num_pixels)
        for i in range(self.num_pixels):
            if i < lit:
                self.pixels[i] = color
            else:
                self.pixels[i] = COLOR_OFF

    def _anim_chase(self, color, elapsed, spacing, period):
        frac = (elapsed % period) / period
        offset = int(frac * spacing) % spacing
        for i in range(self.num_pixels):
            if (i + offset) % spacing == 0:
                self.pixels[i] = color
            else:
                self.pixels[i] = COLOR_OFF

    def _anim_breathing(self, color, elapsed, period):
        # Sine wave mapped from 0..1 for smooth brightness
        phase = (elapsed % period) / period
        brightness = (math.sin(phase * 2.0 * math.pi - math.pi / 2.0) + 1.0) / 2.0
        r = int(color[0] * brightness)
        g = int(color[1] * brightness)
        b = int(color[2] * brightness)
        self.pixels.fill((r, g, b))


# ── Serial reader ──────────────────────────────────────────────────────────

serial = usb_cdc.data
_serial_buf = ""


def read_serial():
    """Read available bytes and return a complete line, or None.

    Accumulates partial reads in *_serial_buf* and splits on newlines.
    Only the first complete line per call is returned; remaining data
    stays in the buffer for the next call.
    """
    global _serial_buf  # noqa: PLW0603 — intentional module-level buffer

    if serial is None:
        return None
    try:
        if serial.in_waiting:
            raw = serial.read(serial.in_waiting)
            if raw:
                _serial_buf += raw.decode("utf-8", "replace")
    except Exception:
        # Serial errors should never crash the firmware
        return None

    newline = _serial_buf.find("\n")
    if newline < 0:
        # Prevent unbounded buffer growth from malformed data
        if len(_serial_buf) > SERIAL_BUF_MAX:
            _serial_buf = ""
        return None

    line = _serial_buf[:newline].strip()
    _serial_buf = _serial_buf[newline + 1:]
    return line if line else None


# ── Initialisation ─────────────────────────────────────────────────────────

pixels = neopixel.NeoPixel(
    NEOPIXEL_PIN,
    NUM_PIXELS,
    brightness=BRIGHTNESS,
    auto_write=False,
    pixel_order=PIXEL_ORDER,
)

# ── Startup animation — quick wipe to confirm the ring is alive ────────
for i in range(NUM_PIXELS):
    pixels[i] = COLOR_WORKING  # Copilot purple
    pixels.show()
    time.sleep(0.02)
time.sleep(0.3)
pixels.fill(COLOR_OFF)
pixels.show()

ring = StatusRing(pixels, NUM_PIXELS)
_gc_counter = 0

# ── Main loop ──────────────────────────────────────────────────────────────

while True:
    line = read_serial()
    if line:
        try:
            msg = json.loads(line)
            state = msg.get("state", "off")
            ring.set_state(state)
        except (ValueError, KeyError):
            pass  # discard malformed JSON

    ring.tick(time.monotonic())

    # Periodic GC to reclaim memory from parsed JSON dicts
    _gc_counter += 1
    if _gc_counter >= 50:  # ~once per second at 50 fps
        gc.collect()
        _gc_counter = 0

    time.sleep(LOOP_DELAY)
