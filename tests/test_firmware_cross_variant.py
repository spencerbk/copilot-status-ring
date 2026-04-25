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
        assert int(match.group(1)) == 300000, "STALE_TIMEOUT_MS must be 300000 (300s)"

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
        assert int(match.group(1)) == 600000, "SERIAL_SILENCE_MS must be 600000 (600s)"

    def test_arduino_has_error_recovery(self) -> None:
        src = _read_arduino_sources()
        assert "consecutiveErrors" in src, "Arduino must track consecutive errors"
        assert "MAX_CONSEC_ERRORS" in src, "Arduino must define MAX_CONSEC_ERRORS"
