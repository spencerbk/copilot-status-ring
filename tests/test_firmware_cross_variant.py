# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Cross-variant consistency: all firmware variants must declare the same states.

The three firmware implementations (CircuitPython, MicroPython, Arduino)
manually duplicate state names, color palettes, and priority tables.  This
test extracts the state name sets from each variant and asserts they match,
catching any state added to one variant but missed in another.
"""

from __future__ import annotations

import ast
import re
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CP_CODE = REPO_ROOT / "firmware" / "circuitpython" / "code.py"
MP_CODE = REPO_ROOT / "firmware" / "micropython" / "main.py"
ARDUINO_DIR = REPO_ROOT / "firmware" / "arduino" / "copilot_command_ring"
ARDUINO_CODE = ARDUINO_DIR / "copilot_command_ring.ino"


def _read_arduino_sources() -> str:
    """Read all Arduino source files (.ino + .h) as a single string."""
    parts = []
    for ext in ("*.ino", "*.h"):
        for p in sorted(ARDUINO_DIR.glob(ext)):
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _extract_python_state_map_keys(path: Path) -> set[str]:
    """Extract STATE_MAP keys from a Python firmware file via AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if "STATE_MAP" in names:
                assert isinstance(node.value, ast.Dict)
                keys: set[str] = set()
                for key in node.value.keys:
                    assert isinstance(key, ast.Constant) and isinstance(key.value, str)
                    keys.add(key.value)
                return keys
    raise AssertionError(f"STATE_MAP not found in {path}")


def _extract_python_priority_keys(path: Path) -> set[str]:
    """Extract STATE_PRIORITY keys from a Python firmware file via AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if "STATE_PRIORITY" in names:
                assert isinstance(node.value, ast.Dict)
                keys: set[str] = set()
                for key in node.value.keys:
                    assert isinstance(key, ast.Constant) and isinstance(key.value, str)
                    keys.add(key.value)
                return keys
    raise AssertionError(f"STATE_PRIORITY not found in {path}")


def _extract_arduino_states(path: Path) -> set[str]:
    """Extract state names from Arduino stateFromStr() strcmp calls."""
    src = _read_arduino_sources()
    # Match: strcmp(s, "state_name") == 0
    return set(re.findall(r'strcmp\(s,\s*"([^"]+)"\)\s*==\s*0', src))


def _load_transient_policy(path: Path) -> types.SimpleNamespace:
    """Load transient-policy symbols from a Python firmware file via AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted = {"NOTIFY_SUPPRESSED_WHILE_BUSY", "should_apply_transient"}
    nodes: list[ast.stmt] = []
    found: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if "NOTIFY_SUPPRESSED_WHILE_BUSY" in names:
                nodes.append(node)
                found.add("NOTIFY_SUPPRESSED_WHILE_BUSY")
        elif isinstance(node, ast.FunctionDef) and node.name == "should_apply_transient":
            nodes.append(node)
            found.add("should_apply_transient")

    missing = wanted - found
    if missing:
        raise AssertionError(f"Missing transient policy symbol(s) in {path}: {sorted(missing)}")

    namespace: dict[str, object] = {}
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)  # noqa: S102
    return types.SimpleNamespace(
        suppressed_when_busy=namespace["NOTIFY_SUPPRESSED_WHILE_BUSY"],
        should_apply_transient=namespace["should_apply_transient"],
    )


def _load_clockwise_head_index(path: Path) -> types.FunctionType:
    """Load the spinner direction helper from Python firmware via AST.

    Executes only the ``_clockwise_head_index`` function definition so the
    hardware-only CircuitPython/MicroPython modules never need importing.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "_clockwise_head_index"
        ),
        None,
    )
    assert node is not None, f"_clockwise_head_index not found in {path}"

    namespace: dict[str, object] = {}
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)  # noqa: S102
    helper = namespace["_clockwise_head_index"]
    assert isinstance(helper, types.FunctionType)
    return helper


# ── STATE_MAP consistency ─────────────────────────────────────────────────


class TestStateMapConsistency:
    """All firmware variants must declare the same set of states."""

    def test_circuitpython_and_micropython_state_maps_match(self) -> None:
        cp = _extract_python_state_map_keys(CP_CODE)
        mp = _extract_python_state_map_keys(MP_CODE)
        only_cp = cp - mp
        only_mp = mp - cp
        assert not only_cp, f"In CircuitPython but not MicroPython: {only_cp}"
        assert not only_mp, f"In MicroPython but not CircuitPython: {only_mp}"

    def test_arduino_recognizes_all_circuitpython_states(self) -> None:
        cp = _extract_python_state_map_keys(CP_CODE)
        ard = _extract_arduino_states(ARDUINO_CODE)
        missing = cp - ard
        assert not missing, f"CircuitPython states missing from Arduino stateFromStr: {missing}"

    def test_arduino_has_no_extra_states(self) -> None:
        cp = _extract_python_state_map_keys(CP_CODE)
        ard = _extract_arduino_states(ARDUINO_CODE)
        extra = ard - cp
        assert not extra, f"Arduino stateFromStr has states not in CircuitPython: {extra}"


# ── STATE_PRIORITY consistency ────────────────────────────────────────────


class TestPriorityConsistency:
    """All firmware variants must have matching STATE_PRIORITY keys and values."""

    def test_priority_keys_match(self) -> None:
        cp = _extract_python_priority_keys(CP_CODE)
        mp = _extract_python_priority_keys(MP_CODE)
        only_cp = cp - mp
        only_mp = mp - cp
        assert not only_cp, f"In CP PRIORITY but not MP: {only_cp}"
        assert not only_mp, f"In MP PRIORITY but not CP: {only_mp}"

    def test_arduino_has_priority_array(self) -> None:
        """Arduino must define a STATE_PRIORITY array with the same ordering."""
        src = _read_arduino_sources()
        assert "STATE_PRIORITY" in src, "Arduino must define STATE_PRIORITY"

    def test_arduino_priority_values_match_circuitpython(self) -> None:
        """Arduino STATE_PRIORITY numeric values must match CircuitPython."""
        src = _read_arduino_sources()
        # Extract the enum order from the State enum
        enum_match = re.search(
            r"enum\s+State\s*:\s*uint8_t\s*\{([^}]+)\}", src
        )
        assert enum_match, "State enum not found in Arduino"
        enum_body = enum_match.group(1)
        enum_names = [
            m.strip().rstrip(",")
            for m in enum_body.split("\n")
            if m.strip() and not m.strip().startswith("//") and m.strip() != "ST_COUNT"
        ]
        enum_names = [n.split(",")[0].strip() for n in enum_names if n]

        # Extract the priority array values (including inline comments)
        prio_match = re.search(
            r"STATE_PRIORITY\[ST_COUNT\]\s*=\s*\{([^}]+)\}", src
        )
        assert prio_match, "STATE_PRIORITY array not found"
        prio_body = prio_match.group(1)
        prio_vals = []
        for line in prio_body.split("\n"):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            # Remove /* ... */ and // comments
            line = re.sub(r"/\*.*?\*/", "", line)
            line = re.sub(r"//.*$", "", line)
            line = line.strip().rstrip(",").strip()
            if line:
                prio_vals.append(int(line))

        # Map enum name -> state string name using stateFromStr
        enum_to_state = {
            "ST_OFF": "off",
            "ST_SESSION_START": "session_start",
            "ST_PROMPT_SUBMITTED": "prompt_submitted",
            "ST_WORKING": "working",
            "ST_TOOL_OK": "tool_ok",
            "ST_TOOL_ERROR": "tool_error",
            "ST_TOOL_DENIED": "tool_denied",
            "ST_AWAITING_PERMISSION": "awaiting_permission",
            "ST_AWAITING_ELICITATION": "awaiting_elicitation",
            "ST_SUBAGENT_ACTIVE": "subagent_active",
            "ST_AGENT_IDLE": "agent_idle",
            "ST_COMPACTING": "compacting",
            "ST_ERROR": "error",
            "ST_NOTIFY": "notify",
            "ST_IDLE": "idle",
        }

        # Build Arduino priority map
        ard_prio: dict[str, int] = {}
        for i, val in enumerate(prio_vals):
            if i < len(enum_names):
                state_name = enum_to_state.get(enum_names[i])
                if state_name:
                    ard_prio[state_name] = val

        # Compare with CircuitPython
        cp_src = CP_CODE.read_text(encoding="utf-8")
        tree = ast.parse(cp_src)
        cp_prio: dict[str, int] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                names = {t.id for t in node.targets if isinstance(t, ast.Name)}
                if "STATE_PRIORITY" in names:
                    assert isinstance(node.value, ast.Dict)
                    for key, val_node in zip(node.value.keys, node.value.values):
                        assert isinstance(key, ast.Constant)
                        assert isinstance(val_node, ast.Constant)
                        cp_prio[key.value] = val_node.value
                    break

        for state_name, cp_val in cp_prio.items():
            ard_val = ard_prio.get(state_name)
            assert ard_val is not None, (
                f"Arduino missing priority for '{state_name}'"
            )
            assert ard_val == cp_val, (
                f"Priority mismatch for '{state_name}': CP={cp_val}, Arduino={ard_val}"
            )


class TestTransientPolicyConsistency:
    """CircuitPython and MicroPython must handle transient overlays the same way."""

    def test_transient_policy_matrix_matches(self) -> None:
        cp = _load_transient_policy(CP_CODE)
        mp = _load_transient_policy(MP_CODE)
        cases = [
            ("working", "notify"),
            ("awaiting_elicitation", "notify"),
            ("awaiting_elicitation", "tool_ok"),
            ("awaiting_elicitation", "tool_error"),
            ("awaiting_elicitation", "tool_denied"),
            ("awaiting_elicitation", "error"),
            ("agent_idle", "notify"),
            ("off", None),
        ]
        for persistent_state, transient in cases:
            cp_result = cp.should_apply_transient(persistent_state, transient)
            mp_result = mp.should_apply_transient(persistent_state, transient)
            assert cp_result == mp_result, (
                "Transient policy mismatch for "
                f"{persistent_state=}, {transient=}: CP={cp_result}, MP={mp_result}"
            )


class TestRuntimeDisplayConfigParity:
    """All firmware variants must accept host-sent display config fields."""

    def test_circuitpython_supports_runtime_display_config(self) -> None:
        src = CP_CODE.read_text(encoding="utf-8")
        assert "apply_runtime_config" in src
        assert '"brightness"' in src
        assert '"pixel_count"' in src
        assert "MAX_RUNTIME_PIXELS" in src

    def test_micropython_supports_runtime_display_config(self) -> None:
        src = MP_CODE.read_text(encoding="utf-8")
        assert "apply_runtime_config" in src
        assert '"brightness"' in src
        assert '"pixel_count"' in src
        assert "MAX_RUNTIME_PIXELS" in src

    def test_arduino_supports_runtime_display_config(self) -> None:
        src = _read_arduino_sources()
        assert "applyRuntimeConfig" in src
        assert "hasBrightness" in src
        assert "hasPixelCount" in src
        assert "updateLength" in src
        assert "MAX_RUNTIME_PIXELS" in src


# ── Arduino feature parity ────────────────────────────────────────────────


class TestArduinoFeatureParity:
    """Arduino firmware must have full feature parity with CircuitPython."""

    def test_arduino_has_session_tracker(self) -> None:
        src = _read_arduino_sources()
        assert "SessionEntry" in src, "Arduino must define SessionEntry struct"
        assert "trackerUpdate" in src, "Arduino must define trackerUpdate()"
        assert "trackerResolve" in src, "Arduino must define trackerResolve()"

    def test_arduino_has_idle_mode(self) -> None:
        src = _read_arduino_sources()
        assert "IDLE_BREATHING" in src, "Arduino must define IDLE_BREATHING"
        assert "IDLE_OFF" in src, "Arduino must define IDLE_OFF"
        assert "globalIdleMode" in src, "Arduino must track global idle mode"

    def test_arduino_has_stale_timeout(self) -> None:
        src = _read_arduino_sources()
        assert "STALE_TIMEOUT_MS" in src, "Arduino must define STALE_TIMEOUT_MS"
        match = re.search(r"STALE_TIMEOUT_MS\s+(\d+)", src)
        assert match, "STALE_TIMEOUT_MS not parseable"
        assert int(match.group(1)) == 1200000, (
            "STALE_TIMEOUT_MS must be 1200000 (1200s / 20 min)"
        )

    def test_arduino_has_max_sessions(self) -> None:
        src = _read_arduino_sources()
        match = re.search(r"MAX_SESSIONS\s+(\d+)", src)
        assert match, "Arduino must define MAX_SESSIONS"
        assert int(match.group(1)) == 8, "MAX_SESSIONS must be 8 (matching CP)"

    def test_arduino_has_ttl_decay(self) -> None:
        src = _read_arduino_sources()
        assert "ttlMs" in src, "Arduino must support TTL in session entries"
        assert "hasTtl" in src, "Arduino must track whether TTL was specified"

    def test_arduino_has_transient_policy(self) -> None:
        src = _read_arduino_sources()
        assert "shouldApplyTransient" in src, (
            "Arduino must define shouldApplyTransient()"
        )
        assert "isTransient" in src, "Arduino must define isTransient()"

    def test_arduino_has_brightness_boost(self) -> None:
        src = _read_arduino_sources()
        assert "BRIGHTNESS_BOOST" in src, "Arduino must define BRIGHTNESS_BOOST"
        assert "isBoosted" in src, "Arduino must define isBoosted()"

    def test_arduino_has_startup_animation(self) -> None:
        src = _read_arduino_sources()
        # CP startup: magenta wipe (20ms per pixel, 300ms hold)
        assert "delay(20)" in src, "Arduino must have 20ms-per-pixel startup wipe"
        assert "delay(300)" in src, "Arduino must have 300ms hold in startup"

    def test_arduino_has_watchdog_support(self) -> None:
        src = _read_arduino_sources()
        assert "HAS_WATCHDOG" in src, "Arduino must define HAS_WATCHDOG"
        assert "wdtInit" in src, "Arduino must define wdtInit()"
        assert "wdtFeed" in src, "Arduino must define wdtFeed()"
        assert "softReset" in src, "Arduino must define softReset()"

    def test_arduino_has_serial_silence_timeout(self) -> None:
        src = _read_arduino_sources()
        assert "SERIAL_SILENCE_MS" in src, "Arduino must define SERIAL_SILENCE_MS"
        match = re.search(r"SERIAL_SILENCE_MS\s+(\d+)", src)
        assert match, "SERIAL_SILENCE_MS not parseable"
        assert int(match.group(1)) == 1500000, (
            "SERIAL_SILENCE_MS must be 1500000 (1500s / 25 min) and ≥ STALE_TIMEOUT_MS"
        )

    def test_arduino_has_error_recovery(self) -> None:
        src = _read_arduino_sources()
        assert "consecutiveErrors" in src, "Arduino must track consecutive errors"
        assert "MAX_CONSEC_ERRORS" in src, "Arduino must define MAX_CONSEC_ERRORS"


# ── Timeout invariants ───────────────────────────────────────────────────


class TestTimeoutInvariants:
    """Cross-variant invariants for STALE_TIMEOUT and SERIAL_SILENCE_TIMEOUT.

    The serial-silence watchdog must be ≥ the stale-prune timeout in every
    firmware variant. Otherwise the USB reload fires before stale pruning
    can run, which clears in-memory tracker state and effectively shortens
    the stale window to ``SERIAL_SILENCE``. See Phase 6 / "ring goes dark"
    investigation for the failure mode.
    """

    def test_circuitpython_silence_geq_stale(self) -> None:
        src = CP_CODE.read_text(encoding="utf-8")
        silence_match = re.search(r"^SERIAL_SILENCE_TIMEOUT\s*=\s*(\d+)", src, re.M)
        stale_match = re.search(r"^STALE_TIMEOUT\s*=\s*(\d+)", src, re.M)
        assert silence_match, "CP must declare SERIAL_SILENCE_TIMEOUT at module scope"
        assert stale_match, "CP must declare STALE_TIMEOUT at module scope"
        silence_s = int(silence_match.group(1))
        stale_s = int(stale_match.group(1))
        assert silence_s >= stale_s, (
            f"CP SERIAL_SILENCE_TIMEOUT ({silence_s}s) must be ≥ STALE_TIMEOUT ({stale_s}s); "
            "otherwise USB reload fires before stale pruning, defeating the prune timeout."
        )

    def test_micropython_silence_geq_stale(self) -> None:
        src = MP_CODE.read_text(encoding="utf-8")
        silence_match = re.search(r"^SERIAL_SILENCE_TIMEOUT_S\s*=\s*(\d+)", src, re.M)
        stale_match = re.search(r"^STALE_TIMEOUT_S\s*=\s*(\d+)", src, re.M)
        assert silence_match, "MP must declare SERIAL_SILENCE_TIMEOUT_S at module scope"
        assert stale_match, "MP must declare STALE_TIMEOUT_S at module scope"
        silence_s = int(silence_match.group(1))
        stale_s = int(stale_match.group(1))
        assert silence_s >= stale_s, (
            f"MP SERIAL_SILENCE_TIMEOUT_S ({silence_s}s) must be ≥ STALE_TIMEOUT_S ({stale_s}s); "
            "otherwise soft_reset fires before stale pruning, defeating the prune timeout."
        )

    def test_arduino_silence_geq_stale(self) -> None:
        src = _read_arduino_sources()
        silence_match = re.search(r"SERIAL_SILENCE_MS\s+(\d+)", src)
        stale_match = re.search(r"STALE_TIMEOUT_MS\s+(\d+)", src)
        assert silence_match, "Arduino must define SERIAL_SILENCE_MS"
        assert stale_match, "Arduino must define STALE_TIMEOUT_MS"
        silence_ms = int(silence_match.group(1))
        stale_ms = int(stale_match.group(1))
        assert silence_ms >= stale_ms, (
            f"Arduino SERIAL_SILENCE_MS ({silence_ms}ms) "
            f"must be ≥ STALE_TIMEOUT_MS ({stale_ms}ms); "
            "otherwise softReset fires before stale pruning, "
            "defeating the prune timeout."
        )

    def test_all_variants_have_same_stale_timeout_in_seconds(self) -> None:
        cp_src = CP_CODE.read_text(encoding="utf-8")
        mp_src = MP_CODE.read_text(encoding="utf-8")
        arduino_src = _read_arduino_sources()
        cp_s = int(re.search(r"^STALE_TIMEOUT\s*=\s*(\d+)", cp_src, re.M).group(1))
        mp_s = int(re.search(r"^STALE_TIMEOUT_S\s*=\s*(\d+)", mp_src, re.M).group(1))
        arduino_ms = int(re.search(r"STALE_TIMEOUT_MS\s+(\d+)", arduino_src).group(1))
        assert cp_s == mp_s == arduino_ms // 1000, (
            f"STALE_TIMEOUT drift: CP={cp_s}s MP={mp_s}s Arduino={arduino_ms // 1000}s"
        )

    def test_all_variants_have_same_serial_silence_in_seconds(self) -> None:
        cp_src = CP_CODE.read_text(encoding="utf-8")
        mp_src = MP_CODE.read_text(encoding="utf-8")
        arduino_src = _read_arduino_sources()
        cp_s = int(
            re.search(r"^SERIAL_SILENCE_TIMEOUT\s*=\s*(\d+)", cp_src, re.M).group(1)
        )
        mp_s = int(
            re.search(r"^SERIAL_SILENCE_TIMEOUT_S\s*=\s*(\d+)", mp_src, re.M).group(1)
        )
        arduino_ms = int(re.search(r"SERIAL_SILENCE_MS\s+(\d+)", arduino_src).group(1))
        assert cp_s == mp_s == arduino_ms // 1000, (
            f"SERIAL_SILENCE drift: CP={cp_s}s MP={mp_s}s Arduino={arduino_ms // 1000}s"
        )


# ── Spinner auto-scale parity ─────────────────────────────────────────────


def _spinner_default_width(num_pixels: int) -> int:
    """The reference formula every firmware variant must implement."""
    return max(2, num_pixels // 4)


class TestSpinnerAutoScaleParity:
    """All firmware variants must auto-scale spinner width with ring size.

    Formula: ``max(2, num_pixels // 4)`` so the segment stays at ~25% of the
    ring (with a floor of 2 LEDs for very small rings). At 24 LEDs this
    yields 6, matching the previous fixed SPINNER_WIDTH so the default 24-LED
    behavior is unchanged.
    """

    def test_reference_formula_values(self) -> None:
        # Source-of-truth sanity table: small rings, 12 / 16 / 24 supported sizes.
        assert _spinner_default_width(8) == 2
        assert _spinner_default_width(12) == 3
        assert _spinner_default_width(16) == 4
        assert _spinner_default_width(24) == 6
        assert _spinner_default_width(60) == 15

    def test_circuitpython_spinner_uses_auto_scale_default(self) -> None:
        src = CP_CODE.read_text(encoding="utf-8")
        # The dispatcher must default width to max(2, self.num_pixels // 4)
        assert re.search(
            r'kwargs\.get\(\s*"width"\s*,\s*max\(\s*2\s*,\s*self\.num_pixels\s*//\s*4\s*\)',
            src,
        ), "CircuitPython spinner dispatcher must use max(2, self.num_pixels // 4) as default"
        # And the working STATE_MAP entry must NOT pin width to a constant
        working_block = re.search(
            r'"working":\s*\(\s*"spinner",\s*COLOR_WORKING,\s*\{([^}]*)\}',
            src,
        )
        assert working_block, "working STATE_MAP entry not found in CircuitPython firmware"
        assert "width" not in working_block.group(1), (
            "working STATE_MAP entry must not pin a width — let the dispatcher auto-scale"
        )

    def test_micropython_spinner_uses_auto_scale_default(self) -> None:
        src = MP_CODE.read_text(encoding="utf-8")
        assert re.search(
            r'kwargs\.get\(\s*"width"\s*,\s*max\(\s*2\s*,\s*self\.num_pixels\s*//\s*4\s*\)',
            src,
        ), "MicroPython spinner dispatcher must use max(2, self.num_pixels // 4) as default"
        working_block = re.search(
            r'"working":\s*\(\s*"spinner",\s*COLOR_WORKING,\s*\{([^}]*)\}',
            src,
        )
        assert working_block, "working STATE_MAP entry not found in MicroPython firmware"
        assert "width" not in working_block.group(1), (
            "working STATE_MAP entry must not pin a width — let the dispatcher auto-scale"
        )

    def test_arduino_spinner_uses_auto_scale_default(self) -> None:
        src = _read_arduino_sources()
        # The ST_WORKING case must derive spinner width from runtimePixelCount / 4
        # with a floor of 2, instead of passing a hard-coded literal like `6`.
        working_block = re.search(
            r"case\s+ST_WORKING\s*:\s*\{?(.*?)break\s*;",
            src,
            re.DOTALL,
        )
        assert working_block, "ST_WORKING case not found in Arduino firmware"
        block_src = working_block.group(1)
        assert "runtimePixelCount / 4" in block_src or "runtimePixelCount/4" in block_src, (
            "Arduino ST_WORKING must derive spinner width from runtimePixelCount / 4"
        )
        assert "< 2" in block_src, (
            "Arduino ST_WORKING must enforce a minimum spinner width of 2 LEDs"
        )
        # Make sure no literal hard-coded width survives the call site
        assert not re.search(r"animSpinner\([^,]+,\s*\d+\s*,", block_src), (
            "Arduino ST_WORKING must not pass a hard-coded literal width to animSpinner"
        )


class TestSpinnerRotationDirection:
    """All firmware variants must rotate the spinner clockwise on Adafruit rings.

    Adafruit's published PCB layouts show pixel indices advance counter-clockwise
    on the 16-pixel ring but clockwise on the 12- and 24-pixel rings. Each
    firmware variant therefore maps forward animation progress to the physical
    index through a ``_clockwise_head_index`` / ``clockwiseHeadIndex`` helper:
    forward for the 12/24 layouts, reversed for the 16 layout, and reversed for
    unknown sizes to preserve prior behavior. These tests lock in that policy and
    catch a refactor that restores the old universal negation.
    """

    def test_python_variants_map_physical_ring_direction(self) -> None:
        for path in (CP_CODE, MP_CODE):
            clockwise_head_index = _load_clockwise_head_index(path)
            # 12/24 rings index clockwise: forward motion is preserved.
            assert clockwise_head_index(1, 12) == 1, path
            assert clockwise_head_index(1, 24) == 1, path
            assert clockwise_head_index(5, 24) == 5, path
            # 16 ring indexes counter-clockwise: motion is reversed.
            assert clockwise_head_index(1, 16) == 15, path
            # Unknown/custom sizes keep the previous reversed behavior.
            assert clockwise_head_index(1, 20) == 19, path
            # Wrap-around holds in both directions.
            assert clockwise_head_index(24, 24) == 0, path
            assert clockwise_head_index(16, 16) == 0, path

    def test_python_variants_spinner_calls_direction_helper(self) -> None:
        for path in (CP_CODE, MP_CODE):
            src = path.read_text(encoding="utf-8")
            match = re.search(
                r"def _anim_spinner\(self.*?(?=\n    def )", src, re.DOTALL,
            )
            assert match, f"_anim_spinner not found in {path}"
            body = match.group(0)
            assert re.search(
                r"forward\s*=\s*int\(\s*frac\s*\*\s*self\.num_pixels\s*\)",
                body,
            ), f"{path} spinner must compute forward = int(frac * self.num_pixels)"
            assert re.search(
                r"head\s*=\s*_clockwise_head_index\(\s*forward\s*,"
                r"\s*self\.num_pixels\s*,?\s*\)",
                body,
            ), f"{path} spinner must derive head via _clockwise_head_index"
            assert (
                "head = (-int(frac * self.num_pixels)) % self.num_pixels"
                not in body
            ), f"{path} spinner must not restore the universal negation"

    def test_arduino_defines_direction_helper(self) -> None:
        src = ARDUINO_CODE.read_text(encoding="utf-8")
        match = re.search(
            r"static int clockwiseHeadIndex\([^)]*\)\s*\{(.*?)\n\}",
            src,
            re.DOTALL,
        )
        assert match, "clockwiseHeadIndex not found in Arduino firmware"
        body = match.group(1)
        # Forward branch for the clockwise-indexed 12/24 rings.
        assert re.search(
            r"pixelCount\s*==\s*12\s*\|\|\s*pixelCount\s*==\s*24", body,
        ), "clockwiseHeadIndex must select forward motion for 12/24 rings"
        assert re.search(
            r"return\s+forward\s*%\s*pixelCount", body,
        ), "clockwiseHeadIndex must preserve forward motion for 12/24 rings"
        # Reversed fallback for the 16 ring and unknown sizes.
        assert re.search(
            r"return\s*\(\s*pixelCount\s*-\s*\(\s*forward\s*%\s*pixelCount\s*\)"
            r"\s*\)\s*%\s*pixelCount",
            body,
        ), "clockwiseHeadIndex must reverse motion in the fallback branch"

    def test_arduino_spinner_calls_direction_helper(self) -> None:
        src = ARDUINO_CODE.read_text(encoding="utf-8")
        match = re.search(
            r"static void animSpinner\([^)]*\)\s*\{(.*?)\n\}",
            src,
            re.DOTALL,
        )
        assert match, "animSpinner not found in Arduino firmware"
        body = match.group(1)
        assert re.search(
            r"int\s+head\s*=\s*clockwiseHeadIndex\(\s*forward\s*,"
            r"\s*runtimePixelCount\s*\)",
            body,
        ), "Arduino spinner must derive head via clockwiseHeadIndex"
        assert "(runtimePixelCount - forward) % runtimePixelCount" not in body, (
            "Arduino spinner must not restore the universal negation"
        )
