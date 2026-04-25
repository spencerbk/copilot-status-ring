# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for the dry-run simulation helper."""

from __future__ import annotations

import json

from copilot_command_ring.config import Config
from copilot_command_ring.simulate import run_sequence


def test_dry_run_prints_json_lines_at_default_verbosity(
    capsys,
    monkeypatch,
) -> None:
    """Dry-run output should show the serial JSON without extra env vars."""
    config = Config(
        brightness=0.25,
        dry_run=True,
        idle_mode="breathing",
        pixel_count=16,
    )
    monkeypatch.setattr(
        "copilot_command_ring.simulate.send_event",
        lambda _config, _message: True,
    )

    run_sequence(config, [("sessionStart", {"source": "new"})], delay=0)

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "event": "sessionStart",
        "state": "session_start",
        "source": "new",
        "ttl_s": 60,
        "idle_mode": "breathing",
        "brightness": 0.25,
        "pixel_count": 16,
    }
    assert "[1/1] sessionStart -> ok" in captured.err
