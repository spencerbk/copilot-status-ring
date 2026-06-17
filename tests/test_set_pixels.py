# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for the ``set-pixels`` subcommand backend (set_pixels.run_set_pixels)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from copilot_command_ring.constants import CONFIG_FILE_NAME, MAX_PIXEL_COUNT
from copilot_command_ring.set_pixels import run_set_pixels


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Bound config resolution to an isolated home + the start dir only.

    Avoids the real-home-leak trap: walking ``tmp_path`` parents would
    traverse the developer's actual ``~`` (tmp lives under it on Windows),
    so the restricted lookup checks only the explicit start directory and
    the isolated home.
    """
    home = tmp_path / "home"
    home.mkdir()

    def _restricted(start: Path) -> Path | None:
        local = Path(start) / CONFIG_FILE_NAME
        if local.is_file():
            return local
        home_candidate = home / CONFIG_FILE_NAME
        return home_candidate if home_candidate.is_file() else None

    monkeypatch.setattr(
        "copilot_command_ring.set_pixels.find_config_path", _restricted
    )
    monkeypatch.setattr(
        "copilot_command_ring.set_pixels._user_home", lambda: home
    )
    return home


def test_creates_global_config_when_none_exists(
    isolated_home: Path, tmp_path: Path
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    assert run_set_pixels(24, config_dir=work) is True
    target = isolated_home / CONFIG_FILE_NAME
    assert json.loads(target.read_text(encoding="utf-8")) == {"pixel_count": 24}
    assert not (work / CONFIG_FILE_NAME).exists()


def test_preserves_existing_fields(isolated_home: Path, tmp_path: Path) -> None:
    target = isolated_home / CONFIG_FILE_NAME
    target.write_text(
        json.dumps({"baud": 115200, "serial_port": "COM12", "pixel_count": 16})
        + "\n",
        encoding="utf-8",
    )
    work = tmp_path / "work"
    work.mkdir()
    assert run_set_pixels(24, config_dir=work) is True
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"baud": 115200, "serial_port": "COM12", "pixel_count": 24}


def test_updates_file_found_in_config_dir(
    isolated_home: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    local = repo / CONFIG_FILE_NAME
    local.write_text(json.dumps({"pixel_count": 16}) + "\n", encoding="utf-8")
    assert run_set_pixels(24, config_dir=repo) is True
    assert json.loads(local.read_text(encoding="utf-8")) == {"pixel_count": 24}
    assert not (isolated_home / CONFIG_FILE_NAME).exists()


@pytest.mark.parametrize("bad", [0, -5])
def test_rejects_non_positive(
    isolated_home: Path, tmp_path: Path, bad: int
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    assert run_set_pixels(bad, config_dir=work) is False
    assert not (isolated_home / CONFIG_FILE_NAME).exists()


def test_rejects_above_max(isolated_home: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    assert run_set_pixels(MAX_PIXEL_COUNT + 1, config_dir=work) is False
    assert not (isolated_home / CONFIG_FILE_NAME).exists()


def test_rejects_bool(isolated_home: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    assert run_set_pixels(True, config_dir=work) is False
    assert not (isolated_home / CONFIG_FILE_NAME).exists()
