# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Copilot Command Ring — MicroPython firmware.

State-machine-driven NeoPixel ring controller. Receives JSON Lines commands
over a dedicated USB CDC data channel (or sys.stdin fallback) and renders
animations on a 24-pixel ring.

Requires MicroPython 1.24+ for USB CDC support on native-USB boards.
On ESP32-C3/C6, falls back to sys.stdin (shared with REPL).

Color palette is kept in sync with:
  - firmware/circuitpython/code.py
  - firmware/arduino/copilot_command_ring/copilot_command_ring.ino
"""

import gc  # noqa: I001
import json
import math
import select
import sys
import time

import machine  # type: ignore[import]

from neopixel_compat import NeoPixelCompat

# ── Configuration ──────────────────────────────────────────────────────────
# Override: set to a specific pin number (e.g., 6) to skip auto-detection.
# Leave as None to let the firmware detect the correct pin for your board.
NEOPIXEL_PIN = None
NUM_PIXELS = 24
BRIGHTNESS = 0.04  # keep low to avoid blinding / power issues
BRIGHTNESS_BOOST = 0.02  # extra brightness for dim states (breathing)
SPINNER_WIDTH = 6  # number of LEDs in the spinner segment
LOOP_DELAY_MS = 20  # ~50 fps
SERIAL_BUF_MAX = 512  # discard buffer if no newline within this many bytes
WATCHDOG_TIMEOUT_MS = 8000  # keep longer than normal render loop latency
MAX_CONSECUTIVE_ERRORS = 10  # force reload after this many consecutive loop failures
SERIAL_SILENCE_TIMEOUT_S = 600  # seconds of zero received bytes → reset when sessions active
DEFAULT_IDLE_MODE = "breathing"  # used when no message has set one yet
STALE_TIMEOUT_S = 300  # seconds before an idle session is pruned

# ── Time helpers (wraparound-safe) ─────────────────────────────────────────
# MicroPython's ticks_ms() wraps at ~12.4 days. All timestamps are stored as
# raw tick ints; elapsed time is computed ONLY via ticks_diff().


def _now():
    """Current time as raw ticks_ms int."""
    return time.ticks_ms()  # type: ignore[attr-defined]


def _elapsed_s(start_ticks):
    """Seconds elapsed since *start_ticks*, wraparound-safe."""
    return time.ticks_diff(time.ticks_ms(), start_ticks) / 1000.0  # type: ignore[attr-defined]


def _elapsed_ms(start_ticks):
    """Milliseconds elapsed since *start_ticks*, wraparound-safe."""
    return time.ticks_diff(time.ticks_ms(), start_ticks)  # type: ignore[attr-defined]


# ── Board auto-detection ───────────────────────────────────────────────────

def _detect_neopixel_pin():
    """Auto-detect the NeoPixel data pin number on boards with stable defaults.

    RP2040/RP2350-family boards in this project normally wire the ring to GPIO 6.
    Other boards use board-specific layouts, so require an explicit
    ``NEOPIXEL_PIN`` override at the top of this file.
    """
    if sys.platform == "rp2":
        return 6  # GP6
    raise RuntimeError(
        "Cannot detect NeoPixel pin on this board — set NEOPIXEL_PIN in main.py"
    )


# ── Color palette ──────────────────────────────────────────────────────────
# Keep in sync with firmware/circuitpython/code.py and
# firmware/arduino/copilot_command_ring/copilot_command_ring.ino
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
COLOR_ELICITATION = (210, 153, 34)     # primer attention (#D29922) — same hue as permission

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
    "awaiting_elicitation": ("pulse",    COLOR_ELICITATION,   {"period": 1.5}),
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

# Suppress white notification flashes while a clearly busy state is visible.
NOTIFY_SUPPRESSED_WHILE_BUSY = {"working", "subagent_active", "compacting"}

# ── Multi-session arbitration ──────────────────────────────────────────────
STATE_PRIORITY = {
    "off": 0,
    "idle": 1,
    "agent_idle": 2,
    "session_start": 3,
    "prompt_submitted": 4,
    "compacting": 5,
    "subagent_active": 6,
    "working": 7,
    "awaiting_permission": 8,
    "awaiting_elicitation": 9,
    "error": 10,
}
MAX_SESSIONS = 8


def should_apply_transient(persistent_state, transient):
    """Return whether *transient* should overlay *persistent_state*."""
    if transient is None:
        return False
    # When the CLI is blocked on user input, keep the elicitation pulse visible
    # unless a hard error occurs.
    if persistent_state == "awaiting_elicitation":
        return transient == "error"
    if transient != "notify":
        return True
    return persistent_state not in NOTIFY_SUPPRESSED_WHILE_BUSY


# ── Animation engine ───────────────────────────────────────────────────────

class StatusRing:
    """Drives a NeoPixel ring through named animation states."""

    def __init__(self, pixels, num_pixels):
        self.pixels = pixels
        self.num_pixels = num_pixels
        self.state = "off"
        self.prev_state = "off"
        self.state_start = _now()
        self.step = 0
        self._saved_state = "off"
        self._saved_start = _now()
        self._saved_step = 0

    def set_state(self, new_state):
        """Transition to *new_state*, recording the previous state."""
        if new_state not in STATE_MAP:
            new_state = "off"
        if new_state == self.state:
            return

        # Returning from a transient flash to the same persistent state —
        # restore saved animation timing so the spinner continues seamlessly.
        if self.state in TRANSIENT_STATES and new_state == self._saved_state:
            entry = STATE_MAP.get(self.state)
            if entry is not None:
                duration = entry[2].get("duration", 0.3)
                if _elapsed_s(self.state_start) < duration:
                    return
            self.prev_state = new_state
            self.state = new_state
            self.state_start = self._saved_start
            self.step = self._saved_step
            if new_state in BOOSTED_STATES:
                self.pixels.brightness = BRIGHTNESS + BRIGHTNESS_BOOST
            return

        # Entering a transient — save current timing only from a
        # non-transient state so nested transients don't overwrite the
        # original persistent animation timing.
        if new_state in TRANSIENT_STATES and self.state not in TRANSIENT_STATES:
            self._saved_state = self.state
            self._saved_start = self.state_start
            self._saved_step = self.step

        self.prev_state = self.state
        self.state = new_state
        self.state_start = _now()
        self.step = 0
        # Boost brightness for dim states, restore for others
        if new_state in BOOSTED_STATES:
            self.pixels.brightness = BRIGHTNESS + BRIGHTNESS_BOOST
        elif self.prev_state in BOOSTED_STATES:
            self.pixels.brightness = BRIGHTNESS

    # ── tick dispatcher ────────────────────────────────────────────────

    def tick(self):
        """Call once per loop iteration."""
        elapsed = _elapsed_s(self.state_start)
        entry = STATE_MAP.get(self.state)
        if entry is None:
            self._anim_off()
            return

        anim_name, color, kwargs = entry

        if anim_name == "off":
            self._anim_off()
        elif anim_name == "flash":
            self._anim_flash(color, elapsed, kwargs.get("duration", 0.3))
        elif anim_name == "blink":
            self._anim_blink(color, elapsed, kwargs.get("period", 0.6))
        elif anim_name == "spinner":
            self._anim_spinner(
                color, elapsed,
                kwargs.get("width", SPINNER_WIDTH),
                kwargs.get("period", 1.0),
            )
        elif anim_name == "wipe":
            self._anim_wipe(color, elapsed, kwargs.get("duration", 0.8))
        elif anim_name == "chase":
            self._anim_chase(
                color, elapsed,
                kwargs.get("spacing", 4),
                kwargs.get("period", 1.0),
            )
        elif anim_name == "breathing":
            self._anim_breathing(color, elapsed, kwargs.get("period", 3.0))
        elif anim_name == "pulse":
            self._anim_pulse(color, elapsed, kwargs.get("period", 1.5))
        elif anim_name == "solid":
            self._anim_solid(color)
        else:
            self._anim_off()

        self.pixels.show()

    # ── helper: revert transient states ────────────────────────────────

    def _revert(self):
        """Return to the previous state (used by flash/transient anims)."""
        target = self._saved_state
        if target in TRANSIENT_STATES:
            target = "off"
        self.prev_state = target
        self.state = target
        if target != "off":
            self.state_start = self._saved_start
            self.step = self._saved_step
        else:
            self.state_start = _now()
            self.step = 0
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
        phase = (elapsed % period) / period
        brightness = (math.sin(phase * 2.0 * math.pi - math.pi / 2.0) + 1.0) / 2.0
        r = int(color[0] * brightness)
        g = int(color[1] * brightness)
        b = int(color[2] * brightness)
        self.pixels.fill((r, g, b))

    def _anim_pulse(self, color, elapsed, period):
        # Sine wave with a raised floor so the ring never fully extinguishes.
        # Visually distinct from breathing (which fades to black) and from
        # blink (which is a hard on/off toggle).
        phase = (elapsed % period) / period
        raw = (math.sin(phase * 2.0 * math.pi - math.pi / 2.0) + 1.0) / 2.0
        brightness = 0.15 + raw * 0.85
        r = int(color[0] * brightness)
        g = int(color[1] * brightness)
        b = int(color[2] * brightness)
        self.pixels.fill((r, g, b))


# ── Multi-session tracker ──────────────────────────────────────────────────

class SessionTracker:
    """Tracks active Copilot CLI sessions and resolves the winning state."""

    def __init__(self):
        self._sessions = {}  # {session_id: [persistent_state, last_seen_ticks, ttl_s_or_None]}
        self._pending_transient = None
        self._idle_mode = DEFAULT_IDLE_MODE
        self._refresh_empty_fallback()

    def _refresh_empty_fallback(self):
        """Apply idle_mode to the no-session fallback state."""
        self._stale_idle = self._idle_mode != "off"

    @property
    def active_count(self):
        return len(self._sessions)

    @property
    def stale_idle(self):
        """True when no live sessions remain and the ring should breathe idle."""
        return self._stale_idle and not self._sessions

    def update(self, session_id, state, now_ticks, ttl_s=None, idle_mode=None):
        """Register or update a session's state."""
        if idle_mode in ("breathing", "off"):
            self._idle_mode = idle_mode
            if not self._sessions:
                self._refresh_empty_fallback()

        if state in TRANSIENT_STATES:
            self._pending_transient = state
            if session_id in self._sessions:
                self._sessions[session_id][1] = now_ticks
            return

        if state == "off":
            self._sessions.pop(session_id, None)
            if not self._sessions:
                self._refresh_empty_fallback()
        else:
            if session_id in self._sessions:
                entry = self._sessions[session_id]
                entry[0] = state
                entry[1] = now_ticks
                entry[2] = ttl_s
            else:
                # Evict oldest if at capacity
                if len(self._sessions) >= MAX_SESSIONS:
                    oldest_id = None
                    oldest_ts = now_ticks
                    for sid, entry in self._sessions.items():
                        age = time.ticks_diff(now_ticks, entry[1])  # type: ignore[attr-defined]
                        oldest_age = time.ticks_diff(now_ticks, oldest_ts)  # type: ignore[attr-defined]
                        if age > oldest_age:
                            oldest_ts = entry[1]
                            oldest_id = sid
                    if oldest_id is not None:
                        del self._sessions[oldest_id]
                self._sessions[session_id] = [state, now_ticks, ttl_s]

    def resolve(self, now_ticks):
        """Return (winning_persistent_state, pending_transient_or_None)."""
        # Prune stale sessions
        pruned = False
        stale_ms = STALE_TIMEOUT_S * 1000
        for sid in list(self._sessions):
            if time.ticks_diff(now_ticks, self._sessions[sid][1]) > stale_ms:  # type: ignore[attr-defined]
                del self._sessions[sid]
                pruned = True

        transient = self._pending_transient
        self._pending_transient = None

        if not self._sessions:
            if pruned:
                self._refresh_empty_fallback()
            if self._stale_idle:
                return "agent_idle", transient
            return "off", transient

        best_state = "off"
        best_priority = -1
        best_time = 0
        for entry in self._sessions.values():
            effective_state = entry[0]
            ttl = entry[2]
            if ttl is not None and ttl > 0 and time.ticks_diff(now_ticks, entry[1]) > ttl * 1000:  # type: ignore[attr-defined]
                    effective_state = "agent_idle"
            p = STATE_PRIORITY.get(effective_state, 0)
            if p > best_priority or (
                p == best_priority
                and time.ticks_diff(entry[1], best_time) > 0  # type: ignore[attr-defined]
            ):
                best_priority = p
                best_state = effective_state
                best_time = entry[1]

        return best_state, transient


# ── Serial reader ──────────────────────────────────────────────────────────

# Determine serial source: CDC data channel or stdin fallback
try:
    import ring_cdc  # type: ignore[import]
    _serial = ring_cdc.cdc_data
except ImportError:
    _serial = None

if _serial is None:
    # Fallback to stdin for ESP32-C3/C6 or when usb-device-cdc is not installed
    try:
        _serial = sys.stdin.buffer
    except AttributeError:
        _serial = sys.stdin

_serial_buf = bytearray()
_legacy_bare_state = None
_poller = select.poll()  # type: ignore[attr-defined]
if _serial is not None:
    _poller.register(_serial, select.POLLIN)  # type: ignore[attr-defined]


def _log_exception(context, exc):
    """Print a concise error to the console."""
    print(context, type(exc).__name__, exc)


def read_serial(tracker):
    """Read available bytes and process messages through the session tracker.

    Returns (has_session_msgs, latest_bare_state, parsed_any).
    """
    global _serial_buf  # noqa: PLW0603

    if _serial is None:
        return False, None, False

    # Non-blocking read via poll
    try:
        events = _poller.poll(0)
        if events:
            raw = _serial.read(256)
            if raw:
                _serial_buf.extend(raw)  # type: ignore[arg-type]
    except Exception as exc:
        _log_exception("serial read error", exc)
        return False, None, False

    # Prevent unbounded buffer growth
    if len(_serial_buf) > SERIAL_BUF_MAX:
        last_nl = _serial_buf.rfind(b"\n")
        _serial_buf = bytearray(_serial_buf[last_nl + 1:]) if last_nl >= 0 else bytearray()
        if len(_serial_buf) > SERIAL_BUF_MAX:
            _serial_buf = bytearray()

    # Drain all complete lines
    has_session_msgs = False
    latest_bare_state = None
    parsed_line = False
    now_ticks = _now()
    while True:
        newline = _serial_buf.find(b"\n")
        if newline < 0:
            break
        parsed_line = True
        line_bytes = bytes(_serial_buf[:newline])
        _serial_buf = bytearray(_serial_buf[newline + 1:])
        try:
            line = line_bytes.decode("utf-8").strip()
            if line:
                msg = json.loads(line)
                state = msg.get("state", "off")
                session_id = msg.get("session")
                ttl_s = msg.get("ttl_s")
                if not isinstance(ttl_s, (int, float)) or ttl_s <= 0:
                    ttl_s = None
                idle_mode = msg.get("idle_mode")
                if idle_mode not in ("breathing", "off"):
                    idle_mode = None
                if session_id is not None:
                    has_session_msgs = True
                    tracker.update(
                        str(session_id), state, now_ticks,
                        ttl_s=ttl_s, idle_mode=idle_mode,
                    )
                else:
                    latest_bare_state = state
                    if idle_mode is not None:
                        tracker._idle_mode = idle_mode  # noqa: SLF001
        except (ValueError, KeyError):
            pass  # discard malformed lines

    return has_session_msgs, latest_bare_state, parsed_line


# ── Initialisation ─────────────────────────────────────────────────────────

_pin_num = NEOPIXEL_PIN if NEOPIXEL_PIN is not None else _detect_neopixel_pin()

pixels = NeoPixelCompat(_pin_num, NUM_PIXELS, brightness=BRIGHTNESS)

# Startup animation — quick wipe to confirm the ring is alive
for i in range(NUM_PIXELS):
    pixels[i] = COLOR_WORKING  # Copilot purple
    pixels.show()
    time.sleep_ms(20)  # type: ignore[attr-defined]
time.sleep_ms(300)  # type: ignore[attr-defined]
pixels.fill(COLOR_OFF)
pixels.show()

ring = StatusRing(pixels, NUM_PIXELS)
tracker = SessionTracker()
_consecutive_errors = 0
_last_rx_ticks = _now()

# Enable hardware watchdog for automatic recovery from hangs.
# machine.WDT is one-way — once started, it cannot be stopped.
_wdt = None
try:  # noqa: SIM105
    _wdt = machine.WDT(timeout=WATCHDOG_TIMEOUT_MS)
except Exception:  # noqa: BLE001
    pass  # watchdog not available on this board

# ── Main loop ──────────────────────────────────────────────────────────────

while True:
    try:
        now_ticks = _now()
        has_sessions, bare_state, parsed_line = read_serial(tracker)
        if parsed_line:
            _last_rx_ticks = now_ticks
        if has_sessions:
            _legacy_bare_state = None
        elif bare_state is not None and bare_state not in TRANSIENT_STATES:
            _legacy_bare_state = bare_state

        if has_sessions or tracker.active_count > 0:
            winning, transient = tracker.resolve(now_ticks)
            ring.set_state(winning)
            if should_apply_transient(winning, transient):
                ring.set_state(transient)
        elif _legacy_bare_state is not None:
            ring.set_state(_legacy_bare_state)
            if (bare_state in TRANSIENT_STATES
                    and should_apply_transient(_legacy_bare_state, bare_state)):
                ring.set_state(bare_state)
        elif bare_state in TRANSIENT_STATES:
            if should_apply_transient(ring.state, bare_state):
                ring.set_state(bare_state)
        elif tracker.stale_idle:
            winning, transient = tracker.resolve(now_ticks)
            ring.set_state(winning)
            if should_apply_transient(winning, transient):
                ring.set_state(transient)

        ring.tick()
        if parsed_line:
            gc.collect()
        _consecutive_errors = 0
    except MemoryError as exc:
        _log_exception("main loop error", exc)
        gc.collect()
        pixels.fill(COLOR_OFF)
        pixels.show()
        ring.set_state("off")
        _consecutive_errors += 1
    except Exception as exc:
        _log_exception("main loop error", exc)
        _consecutive_errors += 1

    # Force full restart if the loop is persistently failing
    if _consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        machine.soft_reset()

    # Serial-silence watchdog
    if (tracker.active_count > 0
            and _elapsed_s(_last_rx_ticks) > SERIAL_SILENCE_TIMEOUT_S):
        machine.soft_reset()

    # Feed the hardware watchdog
    if _wdt is not None:
        _wdt.feed()

    time.sleep_ms(LOOP_DELAY_MS)  # type: ignore[attr-defined]
