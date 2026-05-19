# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Pytest configuration — add host/ to sys.path so imports resolve."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "host"))


@pytest.fixture
def hermetic_config_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Restrict ``find_config_path`` to look only inside *tmp_path*.

    ``find_config_path`` walks the cwd parent chain and then falls back
    to ``~/<CONFIG_FILE_NAME>``.  On a developer machine that has a
    real wizard-saved global config at ``~/.copilot-command-ring.local.json``,
    the parent walk from pytest's ``tmp_path`` (located under
    ``~/AppData/Local/Temp/...`` on Windows or ``/tmp/...`` on Unix) will
    traverse through ``~`` and load the developer's real config, breaking
    test isolation.  Tests that exercise the "no config file" branch (or
    that need a config-file-only-from-tmp guarantee) request this fixture.
    """
    from copilot_command_ring.constants import CONFIG_FILE_NAME

    def _restricted(_start: Path) -> Path | None:
        candidate = tmp_path / CONFIG_FILE_NAME
        return candidate if candidate.is_file() else None

    monkeypatch.setattr(
        "copilot_command_ring.config.find_config_path",
        _restricted,
    )
    return tmp_path
