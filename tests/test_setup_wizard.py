# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for setup-status-ring planning and execution helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

import pytest
from copilot_command_ring.boards import RUNTIME_CIRCUITPYTHON, RUNTIME_MICROPYTHON
from copilot_command_ring.firmware_install import FirmwareInstallError, PreparedFirmware
from copilot_command_ring.setup_wizard import (
    SCOPE_GLOBAL,
    SCOPE_REPO,
    SetupWizardError,
    WizardSelections,
    build_setup_plan,
    default_state_dir,
    execute_setup_plan,
    selections_from_json,
    venv_python_path,
)


def test_default_state_dir_uses_localappdata_on_windows() -> None:
    result = default_state_dir(env={"LOCALAPPDATA": r"C:\Users\me\AppData\Local"}, os_name="nt")
    assert result == Path(r"C:\Users\me\AppData\Local") / "copilot-command-ring"


def test_venv_python_path_uses_windows_scripts_dir() -> None:
    result = venv_python_path(Path(r"C:\ring\.venv"), os_name="nt")
    assert str(result).replace("/", "\\") == r"C:\ring\.venv\Scripts\python.exe"


def test_global_plan_installs_global_hooks(tmp_path: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
    )

    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")

    assert plan.create_venv is True
    assert plan.hook_command.command[-2:] == ("setup", "--force")
    assert plan.install_command.command[-1] == "."


def test_repo_plan_requires_existing_repo_path(tmp_path: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_REPO,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        repo_path=tmp_path / "missing",
    )

    with pytest.raises(SetupWizardError, match="repo_path is not a directory"):
        build_setup_plan(selections, venv_dir=tmp_path / ".venv")


def test_repo_plan_deploys_to_repo(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    selections = WizardSelections(
        scope=SCOPE_REPO,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        repo_path=repo_path,
    )

    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv")

    assert "deploy" in plan.hook_command.command
    assert str(repo_path.resolve()) in plan.hook_command.command


def test_manual_micropython_pin_is_required(tmp_path: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="adafruit-qt-py-rp2040",
        runtime=RUNTIME_MICROPYTHON,
        data_pin=None,
    )

    with pytest.raises(SetupWizardError, match="requires a data pin"):
        build_setup_plan(selections, venv_dir=tmp_path / ".venv")


def test_selections_from_json_parses_paths() -> None:
    selections = selections_from_json(
        '{"scope":"repo","repo_path":"C:/repo","board_id":"raspberry-pi-pico",'
        '"runtime":"circuitpython","data_pin":"board.GP6","approve_firmware":true}'
    )

    assert selections.scope == SCOPE_REPO
    assert selections.repo_path == Path("C:/repo")
    assert selections.approve_firmware is True


def test_execute_setup_plan_runs_expected_commands(tmp_path: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        approve_firmware=False,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    commands: list[tuple[str, ...]] = []

    def fake_runner(command: Sequence[str]) -> None:
        commands.append(tuple(command))

    result = execute_setup_plan(plan, runner=fake_runner)

    assert result.detected_port is None
    assert commands == [
        plan.create_venv_command.command,
        plan.install_command.command,
        plan.hook_command.command,
        plan.validation_command.command,
    ]


def test_execute_setup_plan_can_skip_package_install(tmp_path: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        approve_firmware=False,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    commands: list[tuple[str, ...]] = []

    def fake_runner(command: Sequence[str]) -> None:
        commands.append(tuple(command))

    execute_setup_plan(plan, runner=fake_runner, skip_install=True)

    assert commands == [
        plan.create_venv_command.command,
        plan.hook_command.command,
        plan.validation_command.command,
    ]


def test_execute_setup_plan_can_copy_circuitpython_firmware(tmp_path: Path) -> None:
    target = tmp_path / "CIRCUITPY"
    target.mkdir()
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        approve_firmware=True,
        firmware_target=target,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")

    with patch.object(Path, "exists", return_value=True):
        result = execute_setup_plan(plan, runner=lambda _command: None, output_dir=tmp_path / "out")

    assert target / "boot.py" in result.firmware_written
    assert target / "code.py" in result.firmware_written
    assert result.firmware_warnings == ()


def test_circuitpython_neopixel_warning_does_not_fail_setup(tmp_path: Path) -> None:
    target = tmp_path / "CIRCUITPY"
    target.mkdir()
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        approve_firmware=True,
        firmware_target=target,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")

    def fake_runner(command: Sequence[str]) -> None:
        if "circup" in command:
            raise FirmwareInstallError("circup failed")

    result = execute_setup_plan(plan, runner=fake_runner, output_dir=tmp_path / "out")

    assert target / "boot.py" in result.firmware_written
    assert result.firmware_warnings == ("circup failed",)


def test_manual_firmware_preparation_uses_persistent_output(tmp_path: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        approve_firmware=True,
        firmware_target=None,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    result = execute_setup_plan(plan, runner=lambda _command: None, output_dir=tmp_path / "manual")

    assert result.firmware_prepared_dir == tmp_path / "manual"
    assert (tmp_path / "manual" / "code.py").is_file()


def test_automatic_micropython_install_does_not_report_temp_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_MICROPYTHON,
        data_pin="Pin(6)",
        auto_detect_port=False,
        approve_firmware=True,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    prepared = PreparedFirmware(
        runtime=RUNTIME_MICROPYTHON,
        directory=tmp_path / "prepared",
        files=(tmp_path / "prepared" / "main.py",),
    )
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard.prepare_firmware_files",
        lambda _runtime, _pin, _output: prepared,
    )
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard.install_micropython_files",
        lambda _prepared, _python_executable, *, runner: None,
    )

    result = execute_setup_plan(plan, runner=lambda _command: None)

    assert result.firmware_prepared_dir is None
