# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for setup-status-ring planning and execution helpers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from copilot_command_ring.boards import RUNTIME_CIRCUITPYTHON, RUNTIME_MICROPYTHON
from copilot_command_ring.constants import CONFIG_FILE_NAME, DEFAULT_PIXEL_COUNT
from copilot_command_ring.firmware_install import FirmwareInstallError, PreparedFirmware
from copilot_command_ring.setup_wizard import (
    PACKAGE_SPEC_DEFAULT,
    SCOPE_GLOBAL,
    SCOPE_REPO,
    SetupWizardError,
    WizardSelections,
    _write_local_config,
    build_setup_plan,
    default_package_spec,
    default_state_dir,
    default_venv_dir,
    execute_setup_plan,
    find_repo_root,
    prompt_for_selections,
    selections_from_json,
    venv_python_path,
)


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect setup_wizard's notion of ``Path.home()`` into the test tmp dir.

    This guarantees the local-config writer never touches the developer's real
    home directory during the test run, regardless of which selections are
    used or whether ``execute_setup_plan`` is invoked.
    """
    isolated_home = tmp_path / "home"
    isolated_home.mkdir(exist_ok=True)
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard._user_home",
        lambda: isolated_home,
    )
    return isolated_home


def _make_clone(tmp_path: Path) -> Path:
    """Create a fake copilot-status-ring clone for find_repo_root tests."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "copilot-command-ring"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )
    nested = tmp_path / "host" / "copilot_command_ring"
    nested.mkdir(parents=True)
    return nested


def test_find_repo_root_walks_up_to_pyproject(tmp_path: Path) -> None:
    nested = _make_clone(tmp_path)
    assert find_repo_root(nested / "setup_wizard.py") == tmp_path.resolve()


def test_find_repo_root_returns_none_outside_clone(tmp_path: Path) -> None:
    bare = tmp_path / "elsewhere"
    bare.mkdir()
    assert find_repo_root(bare) is None


def test_find_repo_root_ignores_unrelated_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "some-other-package"\nversion = "1.0"\n',
        encoding="utf-8",
    )
    nested = tmp_path / "src"
    nested.mkdir()
    assert find_repo_root(nested) is None


def test_default_venv_dir_prefers_repo_local_when_in_clone(tmp_path: Path) -> None:
    assert default_venv_dir(repo_root=tmp_path) == tmp_path / ".venv"


def test_default_venv_dir_falls_back_to_state_dir_outside_clone() -> None:
    with patch("copilot_command_ring.setup_wizard.find_repo_root", return_value=None):
        result = default_venv_dir()
    assert result == default_state_dir() / ".venv"


def test_default_package_spec_uses_repo_root_when_in_clone(tmp_path: Path) -> None:
    assert default_package_spec(repo_root=tmp_path) == str(tmp_path)


def test_default_package_spec_falls_back_to_git_url() -> None:
    with patch("copilot_command_ring.setup_wizard.find_repo_root", return_value=None):
        result = default_package_spec()
    assert result == PACKAGE_SPEC_DEFAULT


def test_build_setup_plan_uses_repo_local_defaults(tmp_path: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
    )
    with patch(
        "copilot_command_ring.setup_wizard.find_repo_root", return_value=tmp_path
    ):
        plan = build_setup_plan(selections)
    assert plan.venv_dir == (tmp_path / ".venv").resolve()
    assert plan.install_command.command[-1] == str(tmp_path)


def test_build_setup_plan_falls_back_to_git_url_when_no_clone(tmp_path: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
    )
    with patch("copilot_command_ring.setup_wizard.find_repo_root", return_value=None):
        plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv")
    assert plan.install_command.command[-1] == PACKAGE_SPEC_DEFAULT


def test_build_setup_plan_treats_empty_package_spec_as_default(tmp_path: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
    )
    with patch(
        "copilot_command_ring.setup_wizard.find_repo_root", return_value=tmp_path
    ):
        plan = build_setup_plan(selections, package_spec="")
    assert plan.install_command.command[-1] == str(tmp_path)


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


# ── Ring size: pixel_count plumbing through the wizard ────────────────────


def test_selections_from_json_defaults_pixel_count_when_absent() -> None:
    selections = selections_from_json(
        '{"scope":"global","board_id":"raspberry-pi-pico","runtime":"circuitpython"}'
    )
    assert selections.pixel_count == DEFAULT_PIXEL_COUNT


def test_selections_from_json_parses_explicit_pixel_count() -> None:
    selections = selections_from_json(
        '{"scope":"global","board_id":"raspberry-pi-pico",'
        '"runtime":"circuitpython","pixel_count":16}'
    )
    assert selections.pixel_count == 16


@pytest.mark.parametrize("invalid", [0, -1, -100])
def test_selections_from_json_rejects_non_positive_pixel_count(invalid: int) -> None:
    payload = (
        '{"scope":"global","board_id":"raspberry-pi-pico",'
        f'"runtime":"circuitpython","pixel_count":{invalid}'
        "}"
    )
    with pytest.raises(SetupWizardError, match="pixel_count"):
        selections_from_json(payload)


@pytest.mark.parametrize("invalid", ["abc", "3.14"])
def test_selections_from_json_rejects_non_integer_pixel_count(invalid: str) -> None:
    payload = (
        '{"scope":"global","board_id":"raspberry-pi-pico",'
        f'"runtime":"circuitpython","pixel_count":"{invalid}"'
        "}"
    )
    with pytest.raises(SetupWizardError, match="pixel_count"):
        selections_from_json(payload)


def test_selections_from_json_rejects_boolean_pixel_count() -> None:
    payload = (
        '{"scope":"global","board_id":"raspberry-pi-pico",'
        '"runtime":"circuitpython","pixel_count":true}'
    )
    with pytest.raises(SetupWizardError, match="pixel_count"):
        selections_from_json(payload)


def test_prompt_for_selections_captures_ring_size(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stdin sequence:
    #   1\n          → scope: global
    #   1\n          → board: first option
    #   <enter>      → runtime: default
    #   <enter>      → data pin: default
    #   2\n          → ring size: 16
    #   n\n          → auto-detect serial: no
    stdin = StringIO("1\n1\n\n\n2\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    selections = prompt_for_selections()
    assert selections.pixel_count == 16


def test_prompt_for_selections_default_ring_size_is_24(monkeypatch: pytest.MonkeyPatch) -> None:
    # Same as above but accept the default for the ring-size prompt.
    stdin = StringIO("1\n1\n\n\n\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    selections = prompt_for_selections()
    assert selections.pixel_count == DEFAULT_PIXEL_COUNT


# ── Ring size: local-config writer behavior ───────────────────────────────


def _selections_global(pixel_count: int = DEFAULT_PIXEL_COUNT) -> WizardSelections:
    return WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        pixel_count=pixel_count,
    )


def _selections_repo(repo_path: Path, pixel_count: int) -> WizardSelections:
    return WizardSelections(
        scope=SCOPE_REPO,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        repo_path=repo_path,
        auto_detect_port=False,
        pixel_count=pixel_count,
    )


def test_write_local_config_skips_when_default_and_no_existing_file(
    _isolate_user_home: Path,
) -> None:
    target = _isolate_user_home / CONFIG_FILE_NAME
    assert not target.exists()
    written = _write_local_config(_selections_global(pixel_count=24))
    assert written is None
    assert not target.exists()


def test_write_local_config_writes_non_default_pixel_count_global(
    _isolate_user_home: Path,
) -> None:
    written = _write_local_config(_selections_global(pixel_count=16))
    assert written == _isolate_user_home / CONFIG_FILE_NAME
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload == {"pixel_count": 16}


def test_write_local_config_pins_default_when_existing_file_exists(
    _isolate_user_home: Path,
) -> None:
    target = _isolate_user_home / CONFIG_FILE_NAME
    target.write_text(json.dumps({"baud": 115200}) + "\n", encoding="utf-8")
    written = _write_local_config(_selections_global(pixel_count=24))
    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"baud": 115200, "pixel_count": 24}


def test_write_local_config_preserves_unrelated_fields(_isolate_user_home: Path) -> None:
    target = _isolate_user_home / CONFIG_FILE_NAME
    target.write_text(
        json.dumps({"baud": 115200, "brightness": 0.08, "idle_mode": "off"}) + "\n",
        encoding="utf-8",
    )
    written = _write_local_config(_selections_global(pixel_count=12))
    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {
        "baud": 115200,
        "brightness": 0.08,
        "idle_mode": "off",
        "pixel_count": 12,
    }


def test_write_local_config_repo_scope_writes_into_repo(tmp_path: Path) -> None:
    repo = tmp_path / "myrepo"
    repo.mkdir()
    written = _write_local_config(_selections_repo(repo, pixel_count=16))
    assert written == repo.resolve() / CONFIG_FILE_NAME
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload == {"pixel_count": 16}


def test_write_local_config_recovers_from_corrupt_existing_file(
    _isolate_user_home: Path,
) -> None:
    """A malformed JSON file must not abort the writer; it overwrites cleanly."""
    target = _isolate_user_home / CONFIG_FILE_NAME
    target.write_text("not-json", encoding="utf-8")
    written = _write_local_config(_selections_global(pixel_count=16))
    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"pixel_count": 16}


def test_execute_setup_plan_records_config_written_for_non_default(
    tmp_path: Path,
    _isolate_user_home: Path,
) -> None:
    selections = _selections_global(pixel_count=16)
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    result = execute_setup_plan(plan, runner=lambda _command: None)

    assert result.config_written == _isolate_user_home / CONFIG_FILE_NAME
    payload = json.loads(result.config_written.read_text(encoding="utf-8"))
    assert payload == {"pixel_count": 16}


def test_execute_setup_plan_skips_config_for_default_pixel_count(
    tmp_path: Path,
    _isolate_user_home: Path,
) -> None:
    selections = _selections_global(pixel_count=DEFAULT_PIXEL_COUNT)
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    result = execute_setup_plan(plan, runner=lambda _command: None)

    assert result.config_written is None
    assert not (_isolate_user_home / CONFIG_FILE_NAME).exists()
