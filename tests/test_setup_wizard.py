# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for setup-status-ring planning and execution helpers."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from copilot_command_ring.boards import RUNTIME_CIRCUITPYTHON, RUNTIME_MICROPYTHON
from copilot_command_ring.constants import (
    CONFIG_FILE_NAME,
    DEFAULT_IDLE_MODE,
    DEFAULT_PIXEL_COUNT,
)
from copilot_command_ring.firmware_install import FirmwareInstallError, PreparedFirmware
from copilot_command_ring.setup_wizard import (
    PACKAGE_SPEC_DEFAULT,
    SCOPE_GLOBAL,
    SCOPE_REPO,
    SetupResult,
    SetupWizardError,
    WizardSelections,
    _format_summary,
    _shadow_warning_for,
    _write_local_config,
    build_setup_plan,
    default_package_spec,
    default_state_dir,
    default_venv_dir,
    execute_setup_plan,
    find_repo_root,
    is_local_path_spec,
    prompt_for_selections,
    run_refresh,
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


def test_manual_firmware_preparation_templates_chosen_pixel_count(
    tmp_path: Path,
) -> None:
    # End-to-end: execute_setup_plan must thread selections.pixel_count into
    # prepare_firmware_files so the static firmware boots with the chosen ring
    # size, not just adapt at runtime via host messages.
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        approve_firmware=True,
        firmware_target=None,
        pixel_count=16,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    execute_setup_plan(plan, runner=lambda _command: None, output_dir=tmp_path / "manual")

    code_text = (tmp_path / "manual" / "code.py").read_text(encoding="utf-8")
    assert "NUM_PIXELS = 16" in code_text
    assert "NUM_PIXELS = 24" not in code_text


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
        lambda _runtime, _pin, _output, *, pixel_count=DEFAULT_PIXEL_COUNT: prepared,
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


@pytest.mark.parametrize("oversized", [513, 1024, 999999])
def test_selections_from_json_rejects_oversized_pixel_count(oversized: int) -> None:
    payload = (
        '{"scope":"global","board_id":"raspberry-pi-pico",'
        f'"runtime":"circuitpython","pixel_count":{oversized}'
        "}"
    )
    with pytest.raises(SetupWizardError, match="pixel_count must be <="):
        selections_from_json(payload)


def test_selections_from_json_accepts_max_pixel_count_boundary() -> None:
    from copilot_command_ring.constants import MAX_PIXEL_COUNT

    payload = (
        '{"scope":"global","board_id":"raspberry-pi-pico",'
        f'"runtime":"circuitpython","pixel_count":{MAX_PIXEL_COUNT}'
        "}"
    )
    selections = selections_from_json(payload)
    assert selections.pixel_count == MAX_PIXEL_COUNT


def test_prompt_for_selections_captures_ring_size(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stdin sequence:
    #   1\n          → scope: global
    #   1\n          → board: first option
    #   <enter>      → runtime: default
    #   <enter>      → data pin: default
    #   2\n          → ring size: 16
    #   <enter>      → idle mode: default (breathing)
    #   n\n          → auto-detect serial: no
    stdin = StringIO("1\n1\n\n\n2\n\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    selections = prompt_for_selections()
    assert selections.pixel_count == 16


def test_prompt_for_selections_default_ring_size_is_24(monkeypatch: pytest.MonkeyPatch) -> None:
    # Same as above but accept the default for the ring-size prompt.
    stdin = StringIO("1\n1\n\n\n\n\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    selections = prompt_for_selections()
    assert selections.pixel_count == DEFAULT_PIXEL_COUNT


def test_prompt_for_selections_default_idle_mode_is_breathing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepting the default for the new idle-mode prompt yields breathing."""
    stdin = StringIO("1\n1\n\n\n\n\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    selections = prompt_for_selections()
    assert selections.idle_mode == DEFAULT_IDLE_MODE


def test_prompt_for_selections_picks_idle_mode_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selecting option 2 at the idle-mode prompt picks ``"off"``."""
    stdin = StringIO("1\n1\n\n\n\n2\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    selections = prompt_for_selections()
    assert selections.idle_mode == "off"


# ── Ring size: local-config writer behavior ───────────────────────────────


def _selections_global(
    pixel_count: int = DEFAULT_PIXEL_COUNT,
    *,
    idle_mode: str = DEFAULT_IDLE_MODE,
) -> WizardSelections:
    return WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        pixel_count=pixel_count,
        idle_mode=idle_mode,
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
    """Wizard-unaware fields (baud, brightness) stay put; idle_mode is now
    wizard-aware so it is overwritten with the user's choice from the prompt.
    """
    target = _isolate_user_home / CONFIG_FILE_NAME
    target.write_text(
        json.dumps({"baud": 115200, "brightness": 0.08}) + "\n",
        encoding="utf-8",
    )
    written = _write_local_config(_selections_global(pixel_count=12))
    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {
        "baud": 115200,
        "brightness": 0.08,
        "pixel_count": 12,
    }


def test_write_local_config_overwrites_existing_idle_mode_with_wizard_choice(
    _isolate_user_home: Path,
) -> None:
    """The wizard now surfaces idle_mode as a prompt; an existing stale value
    in the file (e.g. ``"off"`` from an older hand-edited config) is replaced
    by whatever the wizard collected. This is the fix for the "ring goes dark
    even though I ran setup with breathing" symptom.
    """
    target = _isolate_user_home / CONFIG_FILE_NAME
    target.write_text(
        json.dumps({"baud": 115200, "idle_mode": "off"}) + "\n",
        encoding="utf-8",
    )
    written = _write_local_config(_selections_global(pixel_count=24))
    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {
        "baud": 115200,
        "idle_mode": "breathing",
        "pixel_count": 24,
    }


def test_write_local_config_writes_idle_mode_off_when_user_picks_off(
    _isolate_user_home: Path,
) -> None:
    """When the user explicitly picks ``idle_mode = "off"``, the file is
    created (even at default pixel count and no port choice) and the value
    is persisted so the host config layer can read it.
    """
    target = _isolate_user_home / CONFIG_FILE_NAME
    assert not target.exists()
    written = _write_local_config(_selections_global(idle_mode="off"))
    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"pixel_count": DEFAULT_PIXEL_COUNT, "idle_mode": "off"}


def test_write_local_config_default_idle_mode_skips_when_no_other_changes(
    _isolate_user_home: Path,
) -> None:
    """Picking the default idle_mode (``breathing``) alone should not force a
    file into existence — preserves the existing "all defaults → no file"
    contract.
    """
    target = _isolate_user_home / CONFIG_FILE_NAME
    assert not target.exists()
    written = _write_local_config(
        _selections_global(idle_mode=DEFAULT_IDLE_MODE),
    )
    assert written is None
    assert not target.exists()


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


# ── Setup logging: quieter pip, quieter simulate, phase headers, summary ──


def test_install_command_passes_quiet_to_pip(tmp_path: Path) -> None:
    """pip install runs with --quiet so the wizard is silent on success.

    pip's default verbosity dumps ~30 lines per setup. ``--quiet`` keeps only
    warnings and errors. Combined with ``subprocess.run(check=True)`` in
    ``_run_checked``, failures still surface fully via the non-zero exit and
    the captured traceback the caller propagates.
    """
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    assert "--quiet" in plan.install_command.command


def test_validation_command_passes_quiet_to_simulate(tmp_path: Path) -> None:
    """The setup-validation simulate run uses --quiet to suppress JSON dump."""
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    assert "--quiet" in plan.validation_command.command


def test_execute_setup_plan_prints_phase_headers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each major step prints a `==>` phase header so progress is visible."""
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        approve_firmware=False,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")

    execute_setup_plan(plan, runner=lambda _command: None)

    err = capsys.readouterr().err
    assert "==> Creating virtual environment" in err
    assert "==> Installing copilot-command-ring" in err
    assert "==> Validating event pipeline" in err
    # Hook command label is the plan's own label, so we just check the phase prefix.
    assert err.count("==>") >= 4


def test_execute_setup_plan_phase_header_for_port_detection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Port detection is a visible phase when auto_detect_port is on."""
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=True,
        approve_firmware=False,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")

    with patch(
        "copilot_command_ring.setup_wizard.detect_serial_port",
        return_value=None,
    ):
        execute_setup_plan(plan, runner=lambda _command: None)

    err = capsys.readouterr().err
    assert "==> Detecting host serial port" in err


def _bare_result(
    tmp_path: Path,
    *,
    detected_port: str | None = None,
    firmware_written: tuple[Path, ...] = (),
    firmware_prepared_dir: Path | None = None,
    firmware_warnings: tuple[str, ...] = (),
    config_written: Path | None = None,
    pixel_count: int = DEFAULT_PIXEL_COUNT,
    scope: str = SCOPE_GLOBAL,
) -> SetupResult:
    """Build a minimal SetupResult around a plan for summary-format tests."""
    selections = WizardSelections(
        scope=scope,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        pixel_count=pixel_count,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")
    return SetupResult(
        plan=plan,
        detected_port=detected_port,
        firmware_written=firmware_written,
        firmware_prepared_dir=firmware_prepared_dir,
        firmware_warnings=firmware_warnings,
        config_written=config_written,
    )


def test_format_summary_minimal_setup(tmp_path: Path) -> None:
    """Bare summary shows venv, scope, ring size, idle mode, and a Config row
    explaining why no file was written."""
    result = _bare_result(tmp_path)
    lines = _format_summary(
        result,
        pixel_count=DEFAULT_PIXEL_COUNT,
        scope=SCOPE_GLOBAL,
        approve_firmware=False,
    )
    assert lines[0] == "Setup complete."
    body = "\n".join(lines[1:])
    assert "Venv" in body
    assert str(result.plan.venv_dir) in body
    assert "Scope" in body and SCOPE_GLOBAL in body
    assert "24 LEDs" in body
    assert "Idle mode" in body
    assert "Serial port" not in body
    assert "Firmware" not in body
    # New: the bare summary now declares why no config was written.
    assert "Config" in body
    assert "not written" in body


def test_format_summary_includes_detected_port_and_firmware(tmp_path: Path) -> None:
    """Optional rows render only when their fields are populated."""
    target = tmp_path / "CIRCUITPY"
    written = (target / "boot.py", target / "code.py")
    config_path = tmp_path / ".copilot-command-ring.local.json"
    result = _bare_result(
        tmp_path,
        detected_port="COM12",
        firmware_written=written,
        config_written=config_path,
        pixel_count=16,
    )
    lines = _format_summary(
        result,
        pixel_count=16,
        scope=SCOPE_GLOBAL,
        approve_firmware=True,
    )
    body = "\n".join(lines)
    assert "Serial port" in body and "COM12" in body
    assert "Firmware copied" in body and "boot.py" in body and "code.py" in body
    assert "Config" in body and str(config_path) in body
    assert "16 LEDs" in body


def test_format_summary_reports_prepared_firmware_dir(tmp_path: Path) -> None:
    """When firmware is prepared (not copied), surface the prepared directory."""
    prepared = tmp_path / "prepared"
    result = _bare_result(tmp_path, firmware_prepared_dir=prepared)
    lines = _format_summary(
        result,
        pixel_count=DEFAULT_PIXEL_COUNT,
        scope=SCOPE_GLOBAL,
        approve_firmware=True,
    )
    body = "\n".join(lines)
    assert "Firmware prepared" in body
    assert str(prepared) in body


def test_format_summary_renders_firmware_warnings_after_rows(tmp_path: Path) -> None:
    """Firmware warnings appear as their own lines, after the main key/value rows."""
    result = _bare_result(
        tmp_path,
        firmware_written=(tmp_path / "boot.py",),
        firmware_warnings=("circup failed",),
    )
    lines = _format_summary(
        result,
        pixel_count=DEFAULT_PIXEL_COUNT,
        scope=SCOPE_GLOBAL,
        approve_firmware=True,
    )
    assert any("Warning: circup failed" in line for line in lines)


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


# ── Serial port plumbing: WizardSelections + selections_from_mapping ──────


def test_selections_from_json_parses_serial_port() -> None:
    selections = selections_from_json(
        '{"scope":"global","board_id":"raspberry-pi-pico",'
        '"runtime":"circuitpython","serial_port":"COM12"}'
    )
    assert selections.serial_port == "COM12"


def test_selections_from_json_normalizes_blank_serial_port() -> None:
    selections = selections_from_json(
        '{"scope":"global","board_id":"raspberry-pi-pico",'
        '"runtime":"circuitpython","serial_port":"  "}'
    )
    assert selections.serial_port is None


def test_selections_from_json_normalizes_null_serial_port() -> None:
    selections = selections_from_json(
        '{"scope":"global","board_id":"raspberry-pi-pico",'
        '"runtime":"circuitpython","serial_port":null}'
    )
    assert selections.serial_port is None


def test_wizard_selections_to_dict_includes_serial_port() -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=True,
        serial_port="COM7",
    )
    payload = selections.to_dict()
    assert payload["serial_port"] == "COM7"


# ── _write_local_config: serial_port persistence ──────────────────────────


def test_write_local_config_persists_chosen_serial_port(_isolate_user_home: Path) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=True,
        pixel_count=DEFAULT_PIXEL_COUNT,
        serial_port="COM12",
    )
    written = _write_local_config(selections)
    assert written == _isolate_user_home / CONFIG_FILE_NAME
    payload = json.loads(written.read_text(encoding="utf-8"))
    # serial_port writes even when pixel_count is the default and no file
    # pre-existed — the explicit port choice is itself a reason to persist.
    assert payload == {"pixel_count": DEFAULT_PIXEL_COUNT, "serial_port": "COM12"}


def test_write_local_config_skips_when_no_port_and_default_pixels(
    _isolate_user_home: Path,
) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=False,
        pixel_count=DEFAULT_PIXEL_COUNT,
        serial_port=None,
    )
    assert _write_local_config(selections) is None
    assert not (_isolate_user_home / CONFIG_FILE_NAME).exists()


def test_write_local_config_preserves_existing_port_on_skip(
    _isolate_user_home: Path,
) -> None:
    """When the user skips port selection, the existing saved port stays put."""
    target = _isolate_user_home / CONFIG_FILE_NAME
    target.write_text(
        json.dumps({"serial_port": "COM3", "pixel_count": 24}) + "\n",
        encoding="utf-8",
    )
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=True,
        pixel_count=DEFAULT_PIXEL_COUNT,
        serial_port=None,
    )
    written = _write_local_config(selections)
    assert written == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"serial_port": "COM3", "pixel_count": DEFAULT_PIXEL_COUNT}


def test_write_local_config_overrides_existing_port_with_chosen(
    _isolate_user_home: Path,
) -> None:
    target = _isolate_user_home / CONFIG_FILE_NAME
    target.write_text(
        json.dumps({"serial_port": "COM3"}) + "\n",
        encoding="utf-8",
    )
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=True,
        pixel_count=DEFAULT_PIXEL_COUNT,
        serial_port="COM12",
    )
    written = _write_local_config(selections)
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["serial_port"] == "COM12"


# ── idle_mode: selections_from_mapping + validation ───────────────────────


def _idle_mode_payload(idle_mode: object) -> str:
    return json.dumps(
        {
            "scope": SCOPE_GLOBAL,
            "board_id": "raspberry-pi-pico",
            "runtime": RUNTIME_CIRCUITPYTHON,
            "data_pin": "board.GP6",
            "idle_mode": idle_mode,
        }
    )


@pytest.mark.parametrize("idle_mode", ["breathing", "off"])
def test_selections_from_json_accepts_valid_idle_mode(idle_mode: str) -> None:
    selections = selections_from_json(_idle_mode_payload(idle_mode))
    assert selections.idle_mode == idle_mode


def test_selections_from_json_defaults_idle_mode_when_absent() -> None:
    payload = json.dumps(
        {
            "scope": SCOPE_GLOBAL,
            "board_id": "raspberry-pi-pico",
            "runtime": RUNTIME_CIRCUITPYTHON,
            "data_pin": "board.GP6",
        }
    )
    selections = selections_from_json(payload)
    assert selections.idle_mode == DEFAULT_IDLE_MODE


@pytest.mark.parametrize("value", [None, ""])
def test_selections_from_json_treats_missing_or_empty_idle_mode_as_default(
    value: object,
) -> None:
    selections = selections_from_json(_idle_mode_payload(value))
    assert selections.idle_mode == DEFAULT_IDLE_MODE


def test_selections_from_json_normalizes_idle_mode_case_and_whitespace() -> None:
    selections = selections_from_json(_idle_mode_payload("  Off  "))
    assert selections.idle_mode == "off"


@pytest.mark.parametrize("bad", ["dim", "BREATHE", "true", "0", "on"])
def test_selections_from_json_rejects_unknown_idle_mode(bad: str) -> None:
    with pytest.raises(SetupWizardError, match="idle_mode"):
        selections_from_json(_idle_mode_payload(bad))


@pytest.mark.parametrize("bad", [123, 1.5, True, [], {}])
def test_selections_from_json_rejects_non_string_idle_mode(bad: object) -> None:
    with pytest.raises(SetupWizardError, match="idle_mode"):
        selections_from_json(_idle_mode_payload(bad))


def test_to_dict_round_trips_idle_mode() -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        idle_mode="off",
    )
    assert selections.to_dict()["idle_mode"] == "off"


def test_wizard_selections_idle_mode_defaults_to_breathing() -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
    )
    assert selections.idle_mode == DEFAULT_IDLE_MODE


# ── _format_summary + _shadow_warning_for ─────────────────────────────────


def _summary_result(tmp_path: Path) -> SetupResult:
    selections = _selections_global()
    plan = build_setup_plan(
        selections, venv_dir=tmp_path / ".venv", package_spec="."
    )
    return SetupResult(
        plan=plan,
        detected_port=None,
        firmware_written=(),
        firmware_prepared_dir=None,
        firmware_warnings=(),
        config_written=None,
    )


def test_format_summary_includes_idle_mode_row(tmp_path: Path) -> None:
    result = _summary_result(tmp_path)
    lines = _format_summary(
        result,
        pixel_count=24,
        scope=SCOPE_GLOBAL,
        approve_firmware=False,
        idle_mode="off",
    )
    assert any("Idle mode" in line and "off" in line for line in lines), (
        f"Idle mode row missing from summary: {lines}"
    )


def test_format_summary_announces_skipped_config(tmp_path: Path) -> None:
    result = _summary_result(tmp_path)
    lines = _format_summary(
        result,
        pixel_count=DEFAULT_PIXEL_COUNT,
        scope=SCOPE_GLOBAL,
        approve_firmware=False,
        idle_mode=DEFAULT_IDLE_MODE,
    )
    assert any(
        "Config" in line and "not written" in line for line in lines
    ), f"Skip-write annotation missing: {lines}"


def test_shadow_warning_detects_repo_local_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When CWD contains a repo-local config, the helper returns a warning
    naming the shadowing path. This catches the user's reported scenario
    (global setup + stale repo-local file with idle_mode=off)."""
    fake_home = tmp_path / "alt_home"
    fake_home.mkdir()
    repo = fake_home / "myrepo"
    repo.mkdir()
    shadow = repo / CONFIG_FILE_NAME
    shadow.write_text(json.dumps({"idle_mode": "off"}), encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard._user_home", lambda: fake_home
    )

    selections = _selections_global()
    lines = _shadow_warning_for(selections, fake_home / CONFIG_FILE_NAME)
    assert lines is not None
    joined = "\n".join(lines)
    assert "shadow" in joined.lower()
    assert str(shadow) in joined


def test_shadow_warning_silent_when_no_repo_local_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No repo-local file in the CWD-to-home walk → no warning."""
    fake_home = tmp_path / "alt_home"
    fake_home.mkdir()
    elsewhere = fake_home / "project"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard._user_home", lambda: fake_home
    )
    assert _shadow_warning_for(_selections_global(), None) is None


def test_shadow_warning_silent_when_cwd_outside_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If CWD is outside the home tree, ``find_config_path``'s home fallback
    never fires regardless, so no warning is needed and the helper must
    skip the walk to avoid scanning unrelated parts of the filesystem."""
    fake_home = tmp_path / "alt_home"
    fake_home.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    monkeypatch.chdir(outside)
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard._user_home", lambda: fake_home
    )
    assert _shadow_warning_for(_selections_global(), None) is None


def test_shadow_warning_silent_for_repo_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repo-scoped setup intentionally writes a repo-local file, so there is
    nothing to warn about."""
    fake_home = tmp_path / "alt_home"
    fake_home.mkdir()
    repo = fake_home / "myrepo"
    repo.mkdir()
    (repo / CONFIG_FILE_NAME).write_text("{}", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard._user_home", lambda: fake_home
    )
    selections = _selections_repo(repo, pixel_count=16)
    assert _shadow_warning_for(selections, repo / CONFIG_FILE_NAME) is None


def test_shadow_warning_silent_when_only_file_is_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the only existing config file is the home file itself, that is
    not a shadow — that IS the global save the wizard just wrote."""
    fake_home = tmp_path / "alt_home"
    fake_home.mkdir()
    (fake_home / CONFIG_FILE_NAME).write_text("{}", encoding="utf-8")
    project = fake_home / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard._user_home", lambda: fake_home
    )
    assert (
        _shadow_warning_for(_selections_global(), fake_home / CONFIG_FILE_NAME)
        is None
    )


# ── --list-ports-json argparse path ───────────────────────────────────────


def test_list_ports_payload_returns_pyserial_entries() -> None:
    from copilot_command_ring.setup_wizard import list_ports_payload

    with patch(
        "copilot_command_ring.setup_wizard.list_serial_ports",
        return_value=[
            {"device": "COM3", "description": "USB Serial Device"},
            {"device": "COM12", "description": "CircuitPython CDC"},
        ],
    ):
        payload = list_ports_payload()

    assert payload == {
        "ports": [
            {"device": "COM3", "description": "USB Serial Device"},
            {"device": "COM12", "description": "CircuitPython CDC"},
        ],
    }


def test_run_setup_status_ring_handles_list_ports_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import argparse

    from copilot_command_ring.setup_wizard import (
        add_arguments,
        run_setup_status_ring_from_args,
    )

    parser = argparse.ArgumentParser()
    add_arguments(parser)
    args = parser.parse_args(["--list-ports-json"])
    with patch(
        "copilot_command_ring.setup_wizard.list_serial_ports",
        return_value=[{"device": "COM5", "description": "Test Device"}],
    ):
        ok = run_setup_status_ring_from_args(args)
    assert ok is True
    stdout = capsys.readouterr().out
    parsed = json.loads(stdout)
    assert parsed == {"ports": [{"device": "COM5", "description": "Test Device"}]}


# ── execute_setup_plan prefers explicit serial_port over auto-detect ──────


def test_execute_setup_plan_prefers_explicit_serial_port_over_autodetect(
    tmp_path: Path,
) -> None:
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
        auto_detect_port=True,
        serial_port="COM7",
        pixel_count=DEFAULT_PIXEL_COUNT,
    )
    plan = build_setup_plan(selections, venv_dir=tmp_path / ".venv", package_spec=".")

    # Sanity: detect_serial_port must NOT be called when an explicit port is
    # already on the selections — re-detecting would defeat the user's choice.
    with patch(
        "copilot_command_ring.setup_wizard.detect_serial_port",
    ) as detect_mock:
        result = execute_setup_plan(plan, runner=lambda _command: None)

    assert result.detected_port == "COM7"
    detect_mock.assert_not_called()


def test_format_summary_labels_chosen_port_distinctly(tmp_path: Path) -> None:
    """When the summary's port matches the user's choice, label says 'chosen'."""
    result = _bare_result(tmp_path, detected_port="COM7")
    lines = _format_summary(
        result,
        pixel_count=DEFAULT_PIXEL_COUNT,
        scope=SCOPE_GLOBAL,
        approve_firmware=False,
        chosen_port="COM7",
    )
    body = "\n".join(lines)
    assert "COM7 (chosen)" in body
    assert "auto-detected" not in body


# ── Interactive port picker flow ──────────────────────────────────────────


def test_prompt_for_selections_picks_alternate_port_when_autodetect_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Stdin sequence:
    #   1\n          → scope: global
    #   1\n          → board: first option
    #   <enter>      → runtime: default
    #   <enter>      → data pin: default
    #   <enter>      → ring size: default (24)
    #   y\n          → auto-detect serial: yes
    #   2\n          → port flow: "Pick a different port"
    #   2\n          → port list: pick second entry (COM12)
    #   n\n          → approve firmware? no
    stdin = StringIO("1\n1\n\n\n\n\ny\n2\n2\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    with (
        patch(
            "copilot_command_ring.setup_wizard.detect_serial_port",
            return_value="COM3",
        ),
        patch(
            "copilot_command_ring.setup_wizard.list_serial_ports",
            return_value=[
                {"device": "COM3", "description": "Generic USB"},
                {"device": "COM12", "description": "CircuitPython"},
            ],
        ),
    ):
        selections = prompt_for_selections()

    assert selections.auto_detect_port is True
    assert selections.serial_port == "COM12"
    assert selections.approve_firmware is False


def test_prompt_for_selections_uses_autodetected_port_when_user_accepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Choose option 1 at the port-decision prompt ("Use COM3 (auto-detected)").
    stdin = StringIO("1\n1\n\n\n\n\ny\n1\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    with (
        patch(
            "copilot_command_ring.setup_wizard.detect_serial_port",
            return_value="COM3",
        ),
        patch(
            "copilot_command_ring.setup_wizard.list_serial_ports",
            return_value=[{"device": "COM3", "description": "Generic"}],
        ),
    ):
        selections = prompt_for_selections()
    assert selections.serial_port == "COM3"


def test_prompt_for_selections_skip_keeps_no_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Choose option 3 ("Skip") on the port-decision prompt.
    stdin = StringIO("1\n1\n\n\n\n\ny\n3\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    with (
        patch(
            "copilot_command_ring.setup_wizard.detect_serial_port",
            return_value="COM3",
        ),
        patch(
            "copilot_command_ring.setup_wizard.list_serial_ports",
            return_value=[{"device": "COM3", "description": "Generic"}],
        ),
    ):
        selections = prompt_for_selections()
    assert selections.serial_port is None


def test_prompt_for_selections_picks_port_when_autodetect_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # detect_serial_port returns None → 2-option port flow:
    #   1 = "Pick a port from the list"
    #   2 = "Skip — keep any existing saved port"
    # User picks option 1, then chooses the first listed port.
    stdin = StringIO("1\n1\n\n\n\n\ny\n1\n1\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    with (
        patch(
            "copilot_command_ring.setup_wizard.detect_serial_port",
            return_value=None,
        ),
        patch(
            "copilot_command_ring.setup_wizard.list_serial_ports",
            return_value=[{"device": "COM9", "description": "Pico"}],
        ),
    ):
        selections = prompt_for_selections()
    assert selections.serial_port == "COM9"


def test_prompt_for_selections_no_ports_at_all_skips_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # autodetect None + empty list_serial_ports → port picker skips, but the
    # wizard does not abort.
    stdin = StringIO("1\n1\n\n\n\n\ny\nn\n")
    monkeypatch.setattr("sys.stdin", stdin)
    with (
        patch(
            "copilot_command_ring.setup_wizard.detect_serial_port",
            return_value=None,
        ),
        patch(
            "copilot_command_ring.setup_wizard.list_serial_ports",
            return_value=[],
        ),
    ):
        selections = prompt_for_selections()
    assert selections.serial_port is None
    assert selections.auto_detect_port is True


# ── list_serial_ports() unit tests ────────────────────────────────────────


def test_list_serial_ports_returns_sorted_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`list_serial_ports` returns entries sorted by device."""
    import types

    from copilot_command_ring import detect_ports

    class _Port:
        def __init__(self, device: str, description: str) -> None:
            self.device = device
            self.description = description

    fake_serial = types.ModuleType("serial")
    fake_tools = types.ModuleType("serial.tools")
    fake_list_ports = types.ModuleType("serial.tools.list_ports")
    fake_list_ports.comports = lambda: [
        _Port("COM12", "Z device"),
        _Port("COM3", "A device"),
        _Port("COM1", "First device"),
    ]
    monkeypatch.setitem(__import__("sys").modules, "serial", fake_serial)
    monkeypatch.setitem(__import__("sys").modules, "serial.tools", fake_tools)
    monkeypatch.setitem(
        __import__("sys").modules,
        "serial.tools.list_ports",
        fake_list_ports,
    )

    entries = detect_ports.list_serial_ports()
    # Sort is lexicographic by device, matching the implementation.
    assert entries == [
        {"device": "COM1", "description": "First device"},
        {"device": "COM12", "description": "Z device"},
        {"device": "COM3", "description": "A device"},
    ]


def test_list_serial_ports_skips_entries_without_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ports with empty/missing device attribute are filtered out."""
    import types

    from copilot_command_ring import detect_ports

    class _Port:
        def __init__(self, device: str, description: str) -> None:
            self.device = device
            self.description = description

    fake_list_ports = types.ModuleType("serial.tools.list_ports")
    fake_list_ports.comports = lambda: [
        _Port("", "no device id"),
        _Port("COM5", "real device"),
    ]
    monkeypatch.setitem(
        __import__("sys").modules,
        "serial.tools.list_ports",
        fake_list_ports,
    )

    entries = detect_ports.list_serial_ports()
    assert entries == [{"device": "COM5", "description": "real device"}]


def test_list_serial_ports_returns_empty_when_pyserial_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without pyserial the picker collapses to skip, never crashes."""
    import builtins

    from copilot_command_ring import detect_ports

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name.startswith("serial"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert detect_ports.list_serial_ports() == []


def test_list_serial_ports_returns_empty_when_enumeration_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If pyserial's comports() raises, list_serial_ports swallows and returns []."""
    import types

    from copilot_command_ring import detect_ports

    def _boom():
        raise RuntimeError("driver failure")

    fake_list_ports = types.ModuleType("serial.tools.list_ports")
    fake_list_ports.comports = _boom
    monkeypatch.setitem(
        __import__("sys").modules,
        "serial.tools.list_ports",
        fake_list_ports,
    )
    assert detect_ports.list_serial_ports() == []


# ── Option 1: editable install for local clones (`pip install -e`) ────────


def test_is_local_path_spec_recognizes_existing_directory(tmp_path: Path) -> None:
    assert is_local_path_spec(str(tmp_path)) is True


def test_is_local_path_spec_rejects_nonexistent_directory(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert is_local_path_spec(str(missing)) is False


def test_is_local_path_spec_rejects_empty_string() -> None:
    assert is_local_path_spec("") is False


@pytest.mark.parametrize(
    "spec",
    [
        "git+https://github.com/spencerbk/copilot-status-ring.git",
        "https://example.com/pkg.tar.gz",
        "http://example.com/pkg.tar.gz",
        "file:///tmp/wheelhouse/pkg.whl",
        "git+ssh://git@github.com/x/y.git",
    ],
)
def test_is_local_path_spec_rejects_urls_and_vcs(spec: str) -> None:
    assert is_local_path_spec(spec) is False


@pytest.mark.parametrize(
    "spec",
    [
        "copilot-command-ring==0.1.0",
        "copilot-command-ring>=0.1",
        "copilot-command-ring<=2.0",
        "copilot-command-ring~=0.1",
        "copilot-command-ring!=0.1.0",
    ],
)
def test_is_local_path_spec_rejects_version_specifiers(spec: str) -> None:
    assert is_local_path_spec(spec) is False


def test_build_setup_plan_uses_editable_install_for_local_clone(
    tmp_path: Path,
) -> None:
    """When the package spec is a real directory, ``-e`` is injected.

    This is the high-leverage fix from the install-staleness spike: a
    frozen ``pip install <path>`` snapshots the source tree, so a
    later ``git pull`` does not reach the hooks. Editable installs
    point ``site-packages`` at the live source so updates flow
    automatically for contributors with a clone.
    """
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
    )
    plan = build_setup_plan(
        selections, venv_dir=tmp_path / ".venv", package_spec=str(tmp_path),
    )
    command = plan.install_command.command
    assert "-e" in command
    # ``-e <path>`` ordering: the ``-e`` flag must immediately precede the spec
    assert command[command.index("-e") + 1] == str(tmp_path)
    # Last element is still the spec — preserves the contract of older tests.
    assert command[-1] == str(tmp_path)


def test_build_setup_plan_keeps_frozen_install_for_git_url(tmp_path: Path) -> None:
    """The ``git+https://...`` fallback is frozen (no ``-e``).

    Editable installs from a remote VCS URL require ``--src`` and a
    side-checkout directory; supporting that adds complexity that
    end users (who got us here precisely because they don't have a
    clone) don't benefit from. The frozen-install upgrade path for
    those users is the ``refresh`` subcommand.
    """
    selections = WizardSelections(
        scope=SCOPE_GLOBAL,
        board_id="raspberry-pi-pico",
        runtime=RUNTIME_CIRCUITPYTHON,
        data_pin="board.GP6",
    )
    plan = build_setup_plan(
        selections,
        venv_dir=tmp_path / ".venv",
        package_spec=PACKAGE_SPEC_DEFAULT,
    )
    command = plan.install_command.command
    assert "-e" not in command
    assert command[-1] == PACKAGE_SPEC_DEFAULT


# ── Option 2: `copilot-command-ring refresh` ─────────────────────────────


def _writable_venv_python(tmp_path: Path) -> Path:
    """Create a fake venv python executable so ``run_refresh`` clears its
    ``is_file()`` precondition.

    The contents are irrelevant — ``run_refresh`` shells out via the
    injected ``runner`` rather than actually invoking the file.
    """
    venv = tmp_path / ".venv"
    scripts = venv / ("Scripts" if os.name == "nt" else "bin")
    scripts.mkdir(parents=True)
    python_name = "python.exe" if os.name == "nt" else "python"
    python_path = scripts / python_name
    python_path.write_text("# placeholder for tests\n", encoding="utf-8")
    return venv


def test_run_refresh_invokes_pip_install_editable_for_local_clone(
    tmp_path: Path,
) -> None:
    """Local clone → ``pip install -e <repo_root>``."""
    venv = _writable_venv_python(tmp_path)
    captured: list[Sequence[str]] = []

    def _capture(cmd: Sequence[str]) -> None:
        captured.append(list(cmd))

    ok = run_refresh(
        venv_dir=venv,
        package_spec=str(tmp_path),
        runner=_capture,
    )

    assert ok is True
    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[1:5] == ["-m", "pip", "install", "--quiet"]
    assert "--upgrade" in cmd
    assert "-e" in cmd
    assert cmd[-1] == str(tmp_path)


def test_run_refresh_uses_frozen_install_for_git_url(tmp_path: Path) -> None:
    venv = _writable_venv_python(tmp_path)
    captured: list[Sequence[str]] = []

    def _capture(cmd: Sequence[str]) -> None:
        captured.append(list(cmd))

    ok = run_refresh(
        venv_dir=venv,
        package_spec=PACKAGE_SPEC_DEFAULT,
        runner=_capture,
    )

    assert ok is True
    assert "-e" not in captured[0]
    assert captured[0][-1] == PACKAGE_SPEC_DEFAULT


def test_run_refresh_returns_false_when_venv_python_missing(
    tmp_path: Path,
) -> None:
    """No venv → clear actionable error, no pip invocation."""
    captured: list[Sequence[str]] = []

    def _capture(cmd: Sequence[str]) -> None:
        captured.append(list(cmd))

    ok = run_refresh(
        venv_dir=tmp_path / "missing-venv",
        package_spec=str(tmp_path),
        runner=_capture,
    )

    assert ok is False
    assert captured == []


def test_run_refresh_returns_false_when_pip_fails(tmp_path: Path) -> None:
    """Pip non-zero exit propagates as ``False`` for shell-status callers."""
    import subprocess as _subprocess

    venv = _writable_venv_python(tmp_path)

    def _boom(cmd: Sequence[str]) -> None:
        raise _subprocess.CalledProcessError(returncode=1, cmd=list(cmd))

    ok = run_refresh(
        venv_dir=venv,
        package_spec=str(tmp_path),
        runner=_boom,
    )

    assert ok is False


def test_run_refresh_falls_back_to_defaults_when_args_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No explicit args → uses ``default_venv_dir`` + ``default_package_spec``."""
    venv = _writable_venv_python(tmp_path)
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard.default_venv_dir",
        lambda: venv,
    )
    monkeypatch.setattr(
        "copilot_command_ring.setup_wizard.default_package_spec",
        lambda: str(tmp_path),
    )
    captured: list[Sequence[str]] = []
    ok = run_refresh(runner=lambda cmd: captured.append(list(cmd)))
    assert ok is True
    assert captured[0][-1] == str(tmp_path)


