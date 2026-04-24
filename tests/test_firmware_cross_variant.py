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
ARDUINO_CODE = (
    REPO_ROOT
    / "firmware"
    / "arduino"
    / "copilot_command_ring"
    / "copilot_command_ring.ino"
)


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
    src = path.read_text(encoding="utf-8")
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
    """CircuitPython and MicroPython must have matching STATE_PRIORITY keys."""

    def test_priority_keys_match(self) -> None:
        cp = _extract_python_priority_keys(CP_CODE)
        mp = _extract_python_priority_keys(MP_CODE)
        only_cp = cp - mp
        only_mp = mp - cp
        assert not only_cp, f"In CP PRIORITY but not MP: {only_cp}"
        assert not only_mp, f"In MP PRIORITY but not CP: {only_mp}"


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
