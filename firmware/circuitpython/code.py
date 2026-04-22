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
# Override: set to a specific pin (e.g., board.A0) to skip auto-detection.
# Leave as None to let the firmware detect the correct pin for your board.
NEOPIXEL_PIN = None
NUM_PIXELS = 24
BRIGHTNESS = 0.04  # keep low to avoid blinding / power issues
BRIGHTNESS_BOOST = 0.02  # extra brightness for dim states (breathing)
PIXEL_ORDER = neopixel.GRB
SPINNER_WIDTH = 6  # number of LEDs in the spinner segment
LOOP_DELAY = 0.02  # ~50 fps
SERIAL_BUF_MAX = 512  # discard buffer if no newline within this many bytes
WATCHDOG_TIMEOUT = 8  # keep longer than normal render loop latency
MAX_CONSECUTIVE_ERRORS = 10  # force reload after this many consecutive loop failures

# ── Board auto-detection ───────────────────────────────────────────────────

def _detect_neopixel_pin():
    """Auto-detect the NeoPixel data pin from board identity.

    Pin families:
      Pico / Pico W:        board.GP6
      QT Py (all variants):  board.A0  (no D6 on QT Py boards)
      Feather / XIAO / most: board.D6
    """
    bid = getattr(board, "board_id", "")
    if "pico" in bid:
        return board.GP6
    if "qtpy" in bid or "qt_py" in bid:
        return board.A0
    if hasattr(board, "D6"):
        return board.D6
    # Fallback for unlisted boards
    for name in ("GP6", "A0"):
        if hasattr(board, name):
            return getattr(board, name)
    raise RuntimeError("Cannot detect NeoPixel pin — set NEOPIXEL_PIN in code.py")


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

# Suppress white notification flashes while a clearly busy state is already visible.
NOTIFY_SUPPRESSED_WHILE_BUSY = {"working", "subagent_active", "compacting"}

# ── Multi-session arbitration ──────────────────────────────────────────────
# Priority order: higher value = the ring should prefer this state when
# multiple sessions are active.  Only persistent (non-transient) states are
# tracked per-session; transient flashes are shown on top then reverted.
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
    "error": 9,
}
MAX_SESSIONS = 8
STALE_TIMEOUT = 300  # seconds before an idle session is pruned
HARD_OFF_TIMEOUT = 3600  # seconds of stale-idle before ring goes truly dark


def should_apply_transient(persistent_state, transient):
    """Return whether *transient* should overlay *persistent_state*."""
    if transient is None:
        return False
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
        self.state_start = 0.0
        self.step = 0
        self._saved_state = "off"
        self._saved_start = 0.0
        self._saved_step = 0

    def set_state(self, new_state):
        """Transition to *new_state*, recording the previous state.

        When returning from a transient flash to the same persistent
        state, saved animation timing is restored so continuous
        animations (e.g. spinner) resume without a visible restart.
        """
        if new_state not in STATE_MAP:
            new_state = "off"
        if new_state == self.state:
            return

        # Returning from a transient flash to the same persistent state —
        # restore saved animation timing so the spinner continues seamlessly.
        # Wait for the flash animation to finish before restoring, otherwise
        # the main loop's repeated set_state(winning) calls cut it to 1 frame.
        if self.state in TRANSIENT_STATES and new_state == self._saved_state:
            entry = STATE_MAP.get(self.state)
            if entry is not None:
                duration = entry[2].get("duration", 0.3)
                if (time.monotonic() - self.state_start) < duration:
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
        target = self._saved_state
        if target in TRANSIENT_STATES:
            target = "off"
        self.prev_state = target
        self.state = target
        # Restore saved timing so continuous animations resume seamlessly
        if target != "off":
            self.state_start = self._saved_start
            self.step = self._saved_step
        else:
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


# ── Multi-session tracker ──────────────────────────────────────────────────

class SessionTracker:
    """Tracks active Copilot CLI sessions and resolves the winning state.

    Each session is identified by a string ID (typically the CLI process PID).
    The tracker stores each session's last *persistent* state and resolves
    priority across all live sessions.  Transient states (flashes) are
    recorded as pending but do not overwrite the persistent state.
    """

    def __init__(self):
        self._sessions = {}   # {session_id: [persistent_state, last_seen]}
        self._pending_transient = None
        self._last_active_time = 0.0  # last time any session was active
        self._stale_idle = False  # True when sessions emptied by stale pruning

    @property
    def active_count(self):
        return len(self._sessions)

    @property
    def stale_idle(self):
        """True during the post-stale breathing window (before hard off)."""
        if self._sessions or not self._stale_idle:
            return False
        return (time.monotonic() - self._last_active_time) < HARD_OFF_TIMEOUT

    @property
    def had_sessions(self):
        """True if any session was ever tracked."""
        return self._last_active_time > 0.0

    def update(self, session_id, state, now):
        """Register or update a session's state.

        Transient states are stored as a pending flash without changing
        the session's persistent state.  An ``"off"`` state removes
        the session entirely (session ended).
        """
        if state in TRANSIENT_STATES:
            self._pending_transient = state
            # Touch timestamp so the session isn't pruned while active
            if session_id in self._sessions:
                self._sessions[session_id][1] = now
            return

        self._last_active_time = now

        if state == "off":
            self._sessions.pop(session_id, None)
            # Explicit end: if no sessions remain, do NOT enter stale idle
            if not self._sessions:
                self._stale_idle = False
        else:
            if session_id in self._sessions:
                entry = self._sessions[session_id]
                entry[0] = state
                entry[1] = now
            else:
                # Evict oldest if at capacity
                if len(self._sessions) >= MAX_SESSIONS:
                    oldest_id = None
                    oldest_ts = now
                    for sid, entry in self._sessions.items():
                        if entry[1] < oldest_ts:
                            oldest_ts = entry[1]
                            oldest_id = sid
                    if oldest_id is not None:
                        del self._sessions[oldest_id]
                self._sessions[session_id] = [state, now]

    def resolve(self, now):
        """Return ``(winning_persistent_state, pending_transient_or_None)``.

        Prunes stale sessions (no messages within ``STALE_TIMEOUT``),
        then picks the highest-priority persistent state.
        """
        # Prune stale sessions
        pruned = False
        for sid in list(self._sessions):
            if now - self._sessions[sid][1] > STALE_TIMEOUT:
                del self._sessions[sid]
                pruned = True

        transient = self._pending_transient
        self._pending_transient = None

        if not self._sessions:
            # Sessions just emptied by stale pruning → enter stale idle
            if pruned:
                self._stale_idle = True
            # Stale idle window: show dim breathing instead of going dark
            if (self._stale_idle
                    and self._last_active_time > 0.0
                    and (now - self._last_active_time) < HARD_OFF_TIMEOUT):
                return "agent_idle", transient
            return "off", transient

        best_state = "off"
        best_priority = -1
        best_time = 0.0
        for entry in self._sessions.values():
            p = STATE_PRIORITY.get(entry[0], 0)
            if p > best_priority or (p == best_priority and entry[1] > best_time):
                best_priority = p
                best_state = entry[0]
                best_time = entry[1]

        return best_state, transient


# ── Serial reader ──────────────────────────────────────────────────────────

serial = usb_cdc.data
_serial_buf = bytearray()
_was_connected = True


def log_exception(context, exc):
    """Print a concise error to the CircuitPython console."""
    print(context, type(exc).__name__, exc)


def read_serial(tracker):
    """Read available bytes and process messages through the session tracker.

    Drains all complete lines from the buffer each call so that the
    buffer cannot grow without bound under sustained traffic.

    For session-tagged messages, updates the tracker.  For messages
    without a session field, records the latest bare state for backward-
    compatible direct ``set_state`` handling.

    Returns ``(has_session_msgs, latest_bare_state, parsed_any)``.
    """
    global _serial_buf, _was_connected  # noqa: PLW0603

    if serial is None:
        return False, None, False

    # Track USB connection state — only clear buffer on reconnect
    # (a new physical USB connection may carry stale partial data).
    # Do NOT clear or skip reading when disconnected: each hook
    # invocation opens → writes → closes the port quickly, so the
    # MCU frequently sees connected=False while valid data sits in
    # the USB hardware buffer waiting to be read.
    connected = getattr(serial, "connected", True)
    if connected and not _was_connected:
        # Reconnect: discard partial leftovers from old connection
        _serial_buf = bytearray()
    _was_connected = connected

    try:
        if serial.in_waiting:
            raw = serial.read(serial.in_waiting)
            if raw:
                _serial_buf.extend(raw)
    except Exception as exc:
        # Serial errors should never crash the firmware
        log_exception("serial read error", exc)
        return False, None, False

    # Prevent unbounded buffer growth from malformed data (no newlines)
    if len(_serial_buf) > SERIAL_BUF_MAX:
        # Keep only data after the last newline, or discard everything
        last_nl = _serial_buf.rfind(b"\n")
        _serial_buf = bytearray(_serial_buf[last_nl + 1:]) if last_nl >= 0 else bytearray()
        if len(_serial_buf) > SERIAL_BUF_MAX:
            _serial_buf = bytearray()

    # Drain all complete lines
    has_session_msgs = False
    latest_bare_state = None
    parsed_line = False
    now = time.monotonic()
    while True:
        newline = _serial_buf.find(b"\n")
        if newline < 0:
            break
        parsed_line = True
        line_bytes = bytes(_serial_buf[:newline])
        _serial_buf = bytearray(_serial_buf[newline + 1:])
        try:
            line = line_bytes.decode("utf-8", "replace").strip()
            if line:
                msg = json.loads(line)
                state = msg.get("state", "off")
                session_id = msg.get("session")
                if session_id is not None:
                    has_session_msgs = True
                    tracker.update(str(session_id), state, now)
                else:
                    latest_bare_state = state
        except (ValueError, KeyError, UnicodeError):
            pass  # discard malformed lines

    return has_session_msgs, latest_bare_state, parsed_line


# ── Initialisation ─────────────────────────────────────────────────────────

_pin = NEOPIXEL_PIN or _detect_neopixel_pin()

pixels = neopixel.NeoPixel(
    _pin,
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
tracker = SessionTracker()
_consecutive_errors = 0

# Enable hardware watchdog for automatic recovery from hangs
if _WATCHDOG is not None and _WATCHDOG_RESET is not None:
    _WATCHDOG.timeout = WATCHDOG_TIMEOUT
    _WATCHDOG.mode = _WATCHDOG_RESET

# ── Main loop ──────────────────────────────────────────────────────────────

while True:
    try:
        now = time.monotonic()
        has_sessions, bare_state, parsed_line = read_serial(tracker)

        # Resolve session priority whenever live session-tagged messages exist
        # — not only when a new message arrived.  This ensures stale-session
        # pruning runs even if no further messages come (e.g. lost "off"
        # event). Preserve legacy bare-state handling ahead of stale-idle
        # fallback so mixed tagged/untagged traffic still shows current work.
        if has_sessions or tracker.active_count > 0:
            winning, transient = tracker.resolve(now)
            ring.set_state(winning)
            if should_apply_transient(winning, transient):
                ring.set_state(transient)
        elif bare_state is not None:
            ring.set_state(bare_state)
        elif tracker.stale_idle:
            winning, transient = tracker.resolve(now)
            ring.set_state(winning)
            if should_apply_transient(winning, transient):
                ring.set_state(transient)
        elif tracker.had_sessions and ring.state == "agent_idle":
            # Hard off timeout expired after stale idle — go dark
            ring.set_state("off")

        ring.tick(now)
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
