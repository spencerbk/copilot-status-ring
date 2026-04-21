# SPDX-FileCopyrightText: 2024 Copilot Command Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for busy-state transient overlay policy in CircuitPython firmware."""

from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_CODE = REPO_ROOT / "firmware" / "circuitpython" / "code.py"


def _load_transient_policy() -> types.SimpleNamespace:
    """Load transient-policy symbols from firmware without importing hardware deps."""
    tree = ast.parse(FIRMWARE_CODE.read_text(encoding="utf-8"))
    transient_names = {"NOTIFY_SUPPRESSED_WHILE_BUSY", "should_apply_transient"}
    selected_nodes: list[ast.stmt] = []
    found_names: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.Assign):
            target_names = {
                target.id for target in node.targets if isinstance(target, ast.Name)
            }
            if "NOTIFY_SUPPRESSED_WHILE_BUSY" in target_names:
                selected_nodes.append(node)
                found_names.add("NOTIFY_SUPPRESSED_WHILE_BUSY")
        elif isinstance(node, ast.FunctionDef) and node.name == "should_apply_transient":
            selected_nodes.append(node)
            found_names.add("should_apply_transient")

    missing = transient_names - found_names
    if missing:
        names = ", ".join(sorted(missing))
        raise AssertionError(f"Missing transient policy symbol(s) in firmware: {names}")

    namespace: dict[str, object] = {}
    module = ast.Module(body=selected_nodes, type_ignores=[])
    exec(compile(module, str(FIRMWARE_CODE), "exec"), namespace)  # noqa: S102
    return types.SimpleNamespace(
        suppressed_when_busy=namespace["NOTIFY_SUPPRESSED_WHILE_BUSY"],
        should_apply_transient=namespace["should_apply_transient"],
    )


@pytest.mark.parametrize("busy_state", ["working", "subagent_active", "compacting"])
def test_notify_is_suppressed_for_busy_states(busy_state: str) -> None:
    policy = _load_transient_policy()
    assert policy.should_apply_transient(busy_state, "notify") is False


@pytest.mark.parametrize("transient", ["tool_ok", "tool_error", "error"])
def test_non_notify_transients_still_apply_while_busy(transient: str) -> None:
    policy = _load_transient_policy()
    assert policy.should_apply_transient("working", transient) is True


def test_notify_still_applies_when_not_busy() -> None:
    policy = _load_transient_policy()
    assert policy.should_apply_transient("agent_idle", "notify") is True
    assert policy.should_apply_transient("off", None) is False
