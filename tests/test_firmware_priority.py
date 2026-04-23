# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for firmware STATE_PRIORITY ordering and STATE_MAP completeness."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_CODE = REPO_ROOT / "firmware" / "circuitpython" / "code.py"


def _load_firmware_dicts() -> dict[str, dict]:
    """Extract STATE_PRIORITY, STATE_MAP, and TRANSIENT_STATES from firmware via AST."""
    tree = ast.parse(FIRMWARE_CODE.read_text(encoding="utf-8"))
    wanted = {"STATE_PRIORITY", "STATE_MAP", "TRANSIENT_STATES"}
    nodes: list[ast.stmt] = []
    found: set[str] = set()

    # Collect required color constants so STATE_MAP can evaluate
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & wanted:
                nodes.append(node)
                found.update(names & wanted)
            elif any(
                n.startswith(("COLOR_", "SPINNER_")) for n in names
            ):
                nodes.append(node)

    missing = wanted - found
    if missing:
        raise AssertionError(f"Missing symbol(s) in firmware: {', '.join(sorted(missing))}")

    ns: dict[str, object] = {}
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(FIRMWARE_CODE), "exec"), ns)  # noqa: S102
    return {
        "priority": ns["STATE_PRIORITY"],
        "state_map": ns["STATE_MAP"],
        "transient": ns["TRANSIENT_STATES"],
    }


# ── Priority ordering ─────────────────────────────────────────────────────


class TestPriorityOrdering:
    """Relative priority ordering — tests use > / < so they survive renumbering."""

    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.p: dict[str, int] = _load_firmware_dicts()["priority"]

    def test_error_is_highest(self) -> None:
        for state, val in self.p.items():
            if state != "error":
                assert self.p["error"] > val, f"error should outrank {state}"

    def test_awaiting_elicitation_above_awaiting_permission(self) -> None:
        assert self.p["awaiting_elicitation"] > self.p["awaiting_permission"]

    def test_awaiting_elicitation_below_error(self) -> None:
        assert self.p["awaiting_elicitation"] < self.p["error"]

    def test_awaiting_elicitation_above_working(self) -> None:
        assert self.p["awaiting_elicitation"] > self.p["working"]

    def test_working_above_subagent(self) -> None:
        assert self.p["working"] > self.p["subagent_active"]

    def test_off_is_lowest(self) -> None:
        for state, val in self.p.items():
            if state != "off":
                assert val > self.p["off"], f"{state} should outrank off"


# ── STATE_MAP completeness ────────────────────────────────────────────────


class TestStateMapCompleteness:
    """Every state in STATE_PRIORITY has an entry in STATE_MAP."""

    def test_all_priority_states_in_state_map(self) -> None:
        d = _load_firmware_dicts()
        missing = set(d["priority"]) - set(d["state_map"])
        assert not missing, f"States in PRIORITY but not STATE_MAP: {missing}"

    def test_awaiting_elicitation_is_not_transient(self) -> None:
        d = _load_firmware_dicts()
        assert "awaiting_elicitation" not in d["transient"]

    def test_awaiting_elicitation_uses_pulse_animation(self) -> None:
        d = _load_firmware_dicts()
        anim_name = d["state_map"]["awaiting_elicitation"][0]
        assert anim_name == "pulse"
