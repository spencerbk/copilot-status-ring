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
import supervisor  # type: ignore[reportMissingImports]
import usb_cdc  # type: ignore[reportMissingImports]

# Optional watchdog — not all boards support it
try:
    import microcontroller  # type: ignore[reportMissingImports]
    from watchdog import WatchDogMode  # type: ignore[reportMissingImports]

    _WATCHDOG = microcontroller.watchdog
    _WATCHDOG_RESET = WatchDogMode.RESET
except ImportError:
    _WATCHDOG = None
    _WATCHDOG_RESET = None

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
WATCHDOG_TIMEOUT = 8  # keep longer than normal render loop latency
MAX_CONSECUTIVE_ERRORS = 10  # force reload after this many consecutive loop failures

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
_serial_buf = bytearray()
_was_connected = True


def log_exception(context, exc):
    """Print a concise error to the CircuitPython console."""
    print(context, type(exc).__name__, exc)


def read_serial():
    """Read available bytes and return the latest state plus parse activity.

    Drains all complete lines from the buffer each call so that the
    buffer cannot grow without bound under sustained traffic.  Only the
    last received state string is returned (older messages are discarded)
    because only the most recent state matters for the ring.
    """
    global _serial_buf, _was_connected  # noqa: PLW0603

    if serial is None:
        return None, False

    # Clear stale buffer data on USB disconnect/reconnect
    connected = getattr(serial, "connected", True)
    if not connected:
        _was_connected = False
        _serial_buf[:] = b""
        return None, False
    if not _was_connected:
        _was_connected = True
        _serial_buf[:] = b""

    try:
        if serial.in_waiting:
            raw = serial.read(serial.in_waiting)
            if raw:
                _serial_buf.extend(raw)
    except Exception as exc:
        # Serial errors should never crash the firmware
        log_exception("serial read error", exc)
        return None, False

    # Prevent unbounded buffer growth from malformed data (no newlines)
    if len(_serial_buf) > SERIAL_BUF_MAX:
        # Keep only data after the last newline, or discard everything
        last_nl = _serial_buf.rfind(b"\n")
        if last_nl >= 0:
            del _serial_buf[:last_nl + 1]
        else:
            _serial_buf[:] = b""
        if len(_serial_buf) > SERIAL_BUF_MAX:
            _serial_buf[:] = b""

    # Drain all complete lines, keep only the last valid state
    latest_state = None
    parsed_line = False
    while True:
        newline = _serial_buf.find(b"\n")
        if newline < 0:
            break
        parsed_line = True
        line_bytes = bytes(_serial_buf[:newline])
        del _serial_buf[:newline + 1]
        try:
            line = line_bytes.decode("utf-8", "replace").strip()
            if line:
                msg = json.loads(line)
                state = msg.get("state", "off")
                latest_state = state
        except (ValueError, KeyError, UnicodeError):
            pass  # discard malformed lines

    return latest_state, parsed_line


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
_consecutive_errors = 0

# Enable hardware watchdog for automatic recovery from hangs
if _WATCHDOG is not None and _WATCHDOG_RESET is not None:
    _WATCHDOG.timeout = WATCHDOG_TIMEOUT
    _WATCHDOG.mode = _WATCHDOG_RESET

# ── Main loop ──────────────────────────────────────────────────────────────

while True:
    try:
        state, parsed_line = read_serial()
        if state is not None:
            ring.set_state(state)

        ring.tick(time.monotonic())
        if parsed_line:
            gc.collect()
        _consecutive_errors = 0
    except MemoryError as exc:
        # Critical: free memory and reset to safe state
        log_exception("main loop error", exc)
        gc.collect()
        ring.pixels.fill(COLOR_OFF)
        ring.pixels.show()
        ring.set_state("off")
        _consecutive_errors += 1
    except Exception as exc:
        log_exception("main loop error", exc)
        _consecutive_errors += 1

    # Force full restart if the loop is persistently failing
    if _consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        supervisor.reload()

    # Feed the watchdog to prevent reset
    if _WATCHDOG is not None:
        _WATCHDOG.feed()

    time.sleep(LOOP_DELAY)
