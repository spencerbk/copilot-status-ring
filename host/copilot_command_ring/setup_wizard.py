# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Guided setup workflow for Copilot Command Ring."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .boards import (
    RUNTIME_CIRCUITPYTHON,
    default_runtime,
    get_board,
    get_runtime,
    list_boards,
    options_payload,
)
from .config import Config
from .constants import CONFIG_FILE_NAME, DEFAULT_PIXEL_COUNT, MAX_PIXEL_COUNT
from .detect_ports import detect_serial_port, list_serial_ports
from .firmware_install import (
    FirmwareInstallError,
    PreparedFirmware,
    find_circuitpython_drive,
    install_circuitpython_files,
    install_circuitpython_neopixel,
    install_micropython_files,
    prepare_firmware_files,
)

PACKAGE_SPEC_DEFAULT = "git+https://github.com/spencerbk/copilot-status-ring.git"
SCOPE_GLOBAL = "global"
SCOPE_REPO = "repo"

# Heuristic for "the package spec points at a local source tree we can
# install with ``pip install -e ...``". Used so contributors with a
# clone get a live install that auto-updates after ``git pull``; users
# installing from the GitHub URL stay frozen.
_REMOTE_OR_VCS_PREFIXES = (
    "git+",
    "hg+",
    "svn+",
    "bzr+",
    "http://",
    "https://",
    "file://",
)
_VERSION_OPERATORS = ("==", "!=", ">=", "<=", "~=", "===")

_PYPROJECT_NAME_PATTERN = re.compile(
    r"^\s*name\s*=\s*['\"]copilot-command-ring['\"]\s*$",
    re.MULTILINE,
)

Runner = Callable[[Sequence[str]], None]


class SetupWizardError(RuntimeError):
    """Raised when setup wizard input or execution fails."""


@dataclass(frozen=True)
class WizardSelections:
    """Structured user choices collected by CLI or extension UI."""

    scope: str
    board_id: str
    runtime: str
    data_pin: str | None = None
    repo_path: Path | None = None
    auto_detect_port: bool = True
    approve_firmware: bool = False
    firmware_target: Path | None = None
    force_hooks: bool = True
    pixel_count: int = DEFAULT_PIXEL_COUNT
    serial_port: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "scope": self.scope,
            "board_id": self.board_id,
            "runtime": self.runtime,
            "data_pin": self.data_pin,
            "repo_path": str(self.repo_path) if self.repo_path is not None else None,
            "auto_detect_port": self.auto_detect_port,
            "approve_firmware": self.approve_firmware,
            "firmware_target": (
                str(self.firmware_target) if self.firmware_target is not None else None
            ),
            "force_hooks": self.force_hooks,
            "pixel_count": self.pixel_count,
            "serial_port": self.serial_port,
        }


@dataclass(frozen=True)
class CommandStep:
    """One command the setup plan may execute."""

    label: str
    command: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {"label": self.label, "command": list(self.command)}


@dataclass(frozen=True)
class FirmwareActionPlan:
    """Firmware action summary for a setup plan."""

    runtime: str
    board_id: str
    data_pin: str | None
    target: Path | None
    automatic: bool
    manual_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "runtime": self.runtime,
            "board_id": self.board_id,
            "data_pin": self.data_pin,
            "target": str(self.target) if self.target is not None else None,
            "automatic": self.automatic,
            "manual_steps": list(self.manual_steps),
        }


@dataclass(frozen=True)
class SetupPlan:
    """Side-effect-ready setup plan."""

    selections: WizardSelections
    venv_dir: Path
    python_executable: Path
    create_venv: bool
    create_venv_command: CommandStep
    install_command: CommandStep
    hook_command: CommandStep
    validation_command: CommandStep
    firmware: FirmwareActionPlan

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "selections": self.selections.to_dict(),
            "venv_dir": str(self.venv_dir),
            "python_executable": str(self.python_executable),
            "create_venv": self.create_venv,
            "commands": [
                self.create_venv_command.to_dict(),
                self.install_command.to_dict(),
                self.hook_command.to_dict(),
                self.validation_command.to_dict(),
            ],
            "firmware": self.firmware.to_dict(),
        }


@dataclass(frozen=True)
class SetupResult:
    """Summary of executed setup work."""

    plan: SetupPlan
    detected_port: str | None
    firmware_written: tuple[Path, ...] = ()
    firmware_prepared_dir: Path | None = None
    firmware_warnings: tuple[str, ...] = ()
    config_written: Path | None = None


def default_state_dir(
    *,
    env: dict[str, str] | None = None,
    os_name: str | None = None,
) -> Path:
    """Return the stable user-level directory for setup wizard state."""
    environment = env if env is not None else os.environ
    platform_name = os_name if os_name is not None else os.name
    if platform_name == "nt":
        base = environment.get("LOCALAPPDATA")
        if base:
            return Path(base) / "copilot-command-ring"
    else:
        base = environment.get("XDG_DATA_HOME")
        if base:
            return Path(base) / "copilot-command-ring"
    return Path.home() / ".local" / "share" / "copilot-command-ring"


def find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from *start* looking for a copilot-status-ring clone.

    Returns the first ancestor directory whose ``pyproject.toml`` declares
    ``name = "copilot-command-ring"``. Returns ``None`` when no such clone is
    detected (for example, when this module is imported from a wheel that was
    pip-installed into a stand-alone environment).
    """
    origin = (start if start is not None else Path(__file__)).resolve()
    if origin.is_file():
        origin = origin.parent
    for candidate in (origin, *origin.parents):
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            continue
        if _PYPROJECT_NAME_PATTERN.search(text):
            return candidate
    return None


def default_venv_dir(*, repo_root: Path | None = None) -> Path:
    """Return the default dedicated virtual environment path.

    Prefers ``<repo>/.venv`` when this module lives inside a copilot-status-ring
    clone (the slash command and ``install.sh`` always run from a clone). Falls
    back to a user-level path under :func:`default_state_dir` otherwise — for
    example, when ``copilot-command-ring`` was pip-installed standalone.
    """
    root = repo_root if repo_root is not None else find_repo_root()
    if root is not None:
        return root / ".venv"
    return default_state_dir() / ".venv"


def default_package_spec(*, repo_root: Path | None = None) -> str:
    """Return the default pip install spec for the wizard.

    Prefers the local clone path (so ``pip install <repo_root>`` runs offline
    against your working tree) when a clone is detected. Falls back to the
    GitHub URL in :data:`PACKAGE_SPEC_DEFAULT` otherwise.
    """
    root = repo_root if repo_root is not None else find_repo_root()
    if root is not None:
        return str(root)
    return PACKAGE_SPEC_DEFAULT


def is_local_path_spec(spec: str) -> bool:
    """Return ``True`` if *spec* points at a local source tree.

    The wizard adds ``-e`` (editable) to ``pip install`` only when the
    spec is a local path that exists on disk, so contributors working
    from a clone get a live install that auto-updates after
    ``git pull`` while end users installing from the GitHub URL keep
    getting a frozen install (which is the only safe option for a
    remote VCS spec without ``--src``).

    Returns ``False`` for empty strings, URLs / VCS specs
    (``git+...``, ``http(s)://...``, etc.), and PEP 508 version
    specifiers (``copilot-command-ring==0.1.0``).
    """
    if not spec:
        return False
    if spec.startswith(_REMOTE_OR_VCS_PREFIXES):
        return False
    if any(op in spec for op in _VERSION_OPERATORS):
        return False
    try:
        candidate = Path(spec).expanduser()
    except (OSError, ValueError):
        return False
    try:
        return candidate.is_dir()
    except OSError:
        return False


def _build_pip_install_args(
    venv_python: Path, package_spec: str,
) -> tuple[str, ...]:
    """Build the ``pip install`` argv for *package_spec*.

    Injects ``-e`` when the spec is a local source tree so contributors
    get a live install that auto-updates after ``git pull``. Falls back
    to a frozen install for git URLs, version specifiers, or any spec
    that does not resolve to a directory on disk.
    """
    base: tuple[str, ...] = (
        str(venv_python),
        "-m",
        "pip",
        "install",
        "--quiet",
        "--upgrade",
    )
    if is_local_path_spec(package_spec):
        return (*base, "-e", package_spec)
    return (*base, package_spec)


def run_refresh(
    *,
    venv_dir: Path | None = None,
    package_spec: str | None = None,
    runner: Callable[[Sequence[str]], None] | None = None,
) -> bool:
    """Re-install / upgrade the host package into the wizard's venv.

    Designed as the user-facing recovery action for the "I pulled new
    code (or a new release shipped) but the hooks are still running
    the previous version" case: a frozen ``pip install`` freezes the
    source tree, so source-tree edits only reach the hooks once pip
    is re-run. This function performs **only** the pip install step
    that the full wizard performs — no prompts, no firmware copy, no
    hook reinstall, no simulation. It is safe to call after
    ``git pull`` or whenever you suspect the installed package has
    drifted from the source.

    The venv path and package spec resolve the same way they do in
    :func:`build_setup_plan`: defaults come from :func:`default_venv_dir`
    and :func:`default_package_spec`, both of which honor a detected
    repository clone. When the spec is a local source tree the install
    is editable (``pip install -e``); for the GitHub URL fallback it
    is frozen.

    Returns ``True`` on success, ``False`` when pip exits non-zero or
    the venv's python cannot be found.
    """
    chosen_venv = (venv_dir or default_venv_dir()).expanduser().resolve()
    venv_python = venv_python_path(chosen_venv)
    if not venv_python.is_file():
        print(
            f"copilot-command-ring refresh: venv python not found at "
            f"{venv_python}; run `copilot-command-ring setup-status-ring` first.",
            file=sys.stderr,
        )
        return False

    resolved_spec = package_spec if package_spec else default_package_spec()
    args = _build_pip_install_args(venv_python, resolved_spec)
    install_mode = "editable" if "-e" in args else "frozen"

    _phase(
        f"Refreshing copilot-command-ring ({install_mode}, spec={resolved_spec})"
    )
    run = runner if runner is not None else _run_checked
    try:
        run(args)
    except subprocess.CalledProcessError as exc:
        print(
            f"copilot-command-ring refresh: pip install failed "
            f"(exit={exc.returncode}).",
            file=sys.stderr,
        )
        return False
    print("Refresh complete.", file=sys.stderr)
    return True


def venv_python_path(venv_dir: Path, *, os_name: str | None = None) -> Path:
    """Return the Python executable path for *venv_dir*."""
    platform_name = os_name if os_name is not None else os.name
    if platform_name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _bool_value(value: object, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return default


def _coerce_pixel_count(value: object) -> int:
    """Validate and coerce a wizard-input pixel count.

    Accepts ``None`` / missing (default to ``DEFAULT_PIXEL_COUNT``), positive
    integers up to ``MAX_PIXEL_COUNT``, and integer-valued strings within the
    same range. Rejects booleans, non-positive values, oversized values, and
    anything else.
    """
    if value is None or value == "":
        return DEFAULT_PIXEL_COUNT
    if isinstance(value, bool):
        raise SetupWizardError(
            f"pixel_count must be a positive integer, got {value!r}"
        )
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise SetupWizardError(
            f"pixel_count must be a positive integer, got {value!r}"
        ) from exc
    if coerced <= 0:
        raise SetupWizardError(
            f"pixel_count must be a positive integer, got {value!r}"
        )
    if coerced > MAX_PIXEL_COUNT:
        raise SetupWizardError(
            f"pixel_count must be <= {MAX_PIXEL_COUNT}, got {coerced}"
        )
    return coerced


def selections_from_mapping(data: dict[str, object]) -> WizardSelections:
    """Validate and convert extension/JSON input into ``WizardSelections``."""
    scope = str(data.get("scope", SCOPE_GLOBAL)).strip().lower()
    board_id = str(data.get("board_id", "")).strip()
    runtime = str(data.get("runtime", "")).strip().lower()
    if not board_id:
        raise SetupWizardError("board_id is required")
    if not runtime:
        runtime = default_runtime(board_id).runtime

    repo_value = data.get("repo_path")
    repo_path = Path(str(repo_value)).expanduser() if repo_value else None
    target_value = data.get("firmware_target")
    firmware_target = Path(str(target_value)).expanduser() if target_value else None
    pin_value = data.get("data_pin")
    data_pin = str(pin_value).strip() if pin_value not in (None, "") else None
    port_value = data.get("serial_port")
    if port_value is None:
        serial_port: str | None = None
    else:
        port_text = str(port_value).strip()
        serial_port = port_text if port_text else None
    pixel_count = _coerce_pixel_count(data.get("pixel_count"))

    return WizardSelections(
        scope=scope,
        board_id=board_id,
        runtime=runtime,
        data_pin=data_pin,
        repo_path=repo_path,
        auto_detect_port=_bool_value(data.get("auto_detect_port"), default=True),
        approve_firmware=_bool_value(data.get("approve_firmware"), default=False),
        firmware_target=firmware_target,
        force_hooks=_bool_value(data.get("force_hooks"), default=True),
        pixel_count=pixel_count,
        serial_port=serial_port,
    )


def selections_from_json(text: str) -> WizardSelections:
    """Parse JSON into ``WizardSelections``."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SetupWizardError(f"Invalid setup JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SetupWizardError("Setup JSON must be an object")
    return selections_from_mapping(data)


def _validate_selections(selections: WizardSelections) -> None:
    if selections.scope not in {SCOPE_GLOBAL, SCOPE_REPO}:
        raise SetupWizardError("scope must be 'global' or 'repo'")
    if selections.scope == SCOPE_REPO:
        if selections.repo_path is None:
            raise SetupWizardError("repo_path is required for per-repo setup")
        if not selections.repo_path.is_dir():
            raise SetupWizardError(f"repo_path is not a directory: {selections.repo_path}")

    board = get_board(selections.board_id)
    runtime = get_runtime(board.id, selections.runtime)
    if runtime.requires_manual_pin and not selections.data_pin:
        raise SetupWizardError(f"{board.name} with {runtime.label} requires a data pin")


def build_firmware_action_plan(selections: WizardSelections) -> FirmwareActionPlan:
    """Build a firmware summary without performing side effects."""
    runtime = get_runtime(selections.board_id, selections.runtime)
    manual_steps = list(runtime.notes)
    automatic = False

    if selections.runtime == RUNTIME_CIRCUITPYTHON:
        if selections.firmware_target is not None:
            automatic = True
        else:
            manual_steps.append(
                "Mount CIRCUITPY, then copy prepared boot.py/code.py and neopixel.mpy."
            )
    elif runtime.firmware_install == "mpremote":
        automatic = selections.approve_firmware
        manual_steps.append("Flash MicroPython 1.24+ before running mpremote copy steps.")
    else:
        manual_steps.append("Arduino upload remains manual unless you run arduino-cli yourself.")

    return FirmwareActionPlan(
        runtime=selections.runtime,
        board_id=selections.board_id,
        data_pin=selections.data_pin,
        target=selections.firmware_target,
        automatic=automatic,
        manual_steps=tuple(manual_steps),
    )


def build_setup_plan(
    selections: WizardSelections,
    *,
    venv_dir: Path | None = None,
    package_spec: str | None = None,
    base_python: Path | None = None,
) -> SetupPlan:
    """Create a deterministic setup plan from validated selections."""
    _validate_selections(selections)

    chosen_venv = (venv_dir or default_venv_dir()).expanduser().resolve()
    venv_python = venv_python_path(chosen_venv)
    base_python_path = base_python or Path(sys.executable)
    force_flag = ("--force",) if selections.force_hooks else ()
    resolved_package_spec = package_spec if package_spec else default_package_spec()

    if selections.scope == SCOPE_GLOBAL:
        hook_command = CommandStep(
            "Install global Copilot hooks",
            (str(venv_python), "-m", "copilot_command_ring.cli", "setup", *force_flag),
        )
    else:
        assert selections.repo_path is not None
        hook_command = CommandStep(
            "Deploy hooks to one repository",
            (
                str(venv_python),
                "-m",
                "copilot_command_ring.cli",
                "deploy",
                str(selections.repo_path.resolve()),
                *force_flag,
            ),
        )

    return SetupPlan(
        selections=selections,
        venv_dir=chosen_venv,
        python_executable=venv_python,
        create_venv=not venv_python.exists(),
        create_venv_command=CommandStep(
            "Create dedicated virtual environment",
            (str(base_python_path), "-m", "venv", str(chosen_venv)),
        ),
        install_command=CommandStep(
            "Install or upgrade copilot-command-ring",
            _build_pip_install_args(venv_python, resolved_package_spec),
        ),
        hook_command=hook_command,
        validation_command=CommandStep(
            "Run dry-run simulation",
            (
                str(venv_python),
                "-m",
                "copilot_command_ring.simulate",
                "--dry-run",
                "--delay",
                "0",
                "--quiet",
            ),
        ),
        firmware=build_firmware_action_plan(selections),
    )


def _resolve_local_config_path(selections: WizardSelections) -> Path:
    """Return the .copilot-command-ring.local.json path for the chosen scope.

    Global scope writes to ``~/<CONFIG_FILE_NAME>`` so the host bridge picks
    it up on any subsequent invocation under the user's home tree. Repo
    scope writes to ``<repo>/<CONFIG_FILE_NAME>`` so it travels with the
    repository.
    """
    if selections.scope == SCOPE_REPO:
        assert selections.repo_path is not None
        return selections.repo_path.expanduser().resolve() / CONFIG_FILE_NAME
    return _user_home() / CONFIG_FILE_NAME


def _user_home() -> Path:
    """Indirection over ``Path.home()`` so tests can isolate the global path."""
    return Path.home()


def _write_local_config(selections: WizardSelections) -> Path | None:
    """Persist the wizard's pixel_count (and serial_port, if chosen) to the
    local JSON config file.

    Merge semantics: if the target file already exists and parses as a JSON
    object, its existing fields are preserved and only ``pixel_count`` is
    overwritten. When ``selections.serial_port`` is set, it is also merged
    in; when ``selections.serial_port`` is ``None`` (the wizard didn't ask
    or the user chose "skip"), any pre-existing ``serial_port`` in the file
    is left untouched. Returns the path that was written, or ``None`` when
    the wizard chose to skip (default pixel count + no chosen port + no
    existing file).
    """
    target = _resolve_local_config_path(selections)
    existing: dict[str, object] = {}
    file_existed = target.is_file()
    if file_existed:
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            existing = data

    has_chosen_port = selections.serial_port is not None
    if (
        selections.pixel_count == DEFAULT_PIXEL_COUNT
        and not file_existed
        and not has_chosen_port
    ):
        return None

    existing["pixel_count"] = selections.pixel_count
    if has_chosen_port:
        existing["serial_port"] = selections.serial_port
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return target


def _run_checked(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def _phase(label: str) -> None:
    """Print a setup phase header to stderr.

    Phase headers give the user a visible progress trail when the underlying
    commands (``pip install --quiet``, ``simulate --quiet``, …) are silent on
    success. Keep them short, terminal-friendly, and on stderr so they do not
    pollute JSON-on-stdout commands like ``--plan-only``.
    """
    print(f"==> {label}", file=sys.stderr)


def _firmware_output_dir(plan: SetupPlan, output_dir: Path | None) -> Path | None:
    if output_dir is not None:
        return output_dir
    if plan.firmware.automatic:
        return None
    return default_state_dir() / "firmware" / plan.selections.runtime


def _install_circuitpython_to_target(
    prepared: PreparedFirmware,
    target: Path,
    python_executable: Path,
    *,
    runner: Runner,
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    written = install_circuitpython_files(prepared, target)
    try:
        install_circuitpython_neopixel(target, python_executable, runner=runner)
    except FirmwareInstallError as exc:
        return written, (str(exc),)
    return written, ()


def execute_setup_plan(
    plan: SetupPlan,
    *,
    runner: Runner = _run_checked,
    output_dir: Path | None = None,
    skip_install: bool = False,
) -> SetupResult:
    """Execute a setup plan and return a summary."""
    if plan.create_venv:
        _phase(f"Creating virtual environment at {plan.venv_dir}")
        runner(plan.create_venv_command.command)
    if not skip_install:
        _phase("Installing copilot-command-ring (this may take a minute)")
        runner(plan.install_command.command)
    _phase(plan.hook_command.label)
    runner(plan.hook_command.command)

    detected_port: str | None = None
    if plan.selections.serial_port:
        # When the wizard collected an explicit port, prefer it for the
        # summary instead of re-detecting — re-detection might pick a
        # different port (e.g. the one the user just rejected).
        detected_port = plan.selections.serial_port
    elif plan.selections.auto_detect_port:
        _phase("Detecting host serial port")
        detected_port = detect_serial_port(Config())
    firmware_written: tuple[Path, ...] = ()
    prepared_dir: Path | None = None
    firmware_warnings: tuple[str, ...] = ()

    if plan.selections.approve_firmware:
        _phase(f"Preparing {plan.selections.runtime} firmware")
        persistent_output = _firmware_output_dir(plan, output_dir)
        if persistent_output is None:
            with tempfile.TemporaryDirectory(prefix="copilot-ring-firmware-") as temp_dir:
                prepared = prepare_firmware_files(
                    plan.selections.runtime,
                    plan.selections.data_pin,
                    Path(temp_dir),
                    pixel_count=plan.selections.pixel_count,
                )
                if plan.selections.runtime == RUNTIME_CIRCUITPYTHON:
                    if plan.selections.firmware_target is not None:
                        firmware_written, firmware_warnings = _install_circuitpython_to_target(
                            prepared,
                            plan.selections.firmware_target,
                            plan.python_executable,
                            runner=runner,
                        )
                elif plan.firmware.automatic:
                    install_micropython_files(
                        prepared,
                        plan.python_executable,
                        runner=runner,
                    )
        else:
            prepared = prepare_firmware_files(
                plan.selections.runtime,
                plan.selections.data_pin,
                persistent_output,
                pixel_count=plan.selections.pixel_count,
            )
            prepared_dir = prepared.directory
            if plan.selections.runtime == RUNTIME_CIRCUITPYTHON:
                if plan.selections.firmware_target is not None:
                    firmware_written, firmware_warnings = _install_circuitpython_to_target(
                        prepared,
                        plan.selections.firmware_target,
                        plan.python_executable,
                        runner=runner,
                    )
            elif plan.firmware.automatic:
                install_micropython_files(
                    prepared,
                    plan.python_executable,
                    runner=runner,
                )

    _phase("Validating event pipeline")
    runner(plan.validation_command.command)
    config_written = _write_local_config(plan.selections)
    return SetupResult(
        plan=plan,
        detected_port=detected_port,
        firmware_written=firmware_written,
        firmware_prepared_dir=prepared_dir,
        firmware_warnings=firmware_warnings,
        config_written=config_written,
    )


def detect_port_payload() -> dict[str, object]:
    """Return JSON-ready serial detection status."""
    port = detect_serial_port(Config())
    return {"detected": port is not None, "port": port}


def detect_circuitpy_payload() -> dict[str, object]:
    """Return JSON-ready CIRCUITPY drive detection status."""
    drive = find_circuitpython_drive()
    return {"detected": drive is not None, "path": str(drive) if drive is not None else None}


def list_ports_payload() -> dict[str, object]:
    """Return JSON-ready list of every enumerable serial port.

    Each entry has a ``device`` (e.g. ``COM12``) and a ``description``.
    The extension calls this when the user wants to manually pick a port
    after rejecting auto-detection or when no matching device was found.
    Returns an empty list (not an error) when pyserial is unavailable.
    """
    return {"ports": list_serial_ports()}


def _choose(prompt: str, options: Sequence[tuple[str, str]], *, default: str) -> str:
    print(prompt)
    for index, (_, label) in enumerate(options, start=1):
        print(f"  {index}. {label}")
    default_index = next(
        (index for index, (value, _) in enumerate(options, start=1) if value == default),
        1,
    )
    answer = input(f"Choose [{default_index}]: ").strip()
    if not answer:
        return default
    try:
        choice = int(answer)
    except ValueError as exc:
        raise SetupWizardError("Choose a numbered option") from exc
    if not 1 <= choice <= len(options):
        raise SetupWizardError("Choice is out of range")
    return options[choice - 1][0]


def _confirm(prompt: str, *, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{prompt} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def _pick_serial_port_interactively(
    *,
    auto_detected: str | None,
) -> str | None:
    """Prompt the user to choose a serial port for the setup config.

    The flow always offers a "Skip" outcome so the user can leave any
    pre-existing configured port untouched. Returns the chosen port
    device string (e.g. ``"COM12"``) or ``None`` if the user skipped or
    no ports were enumerable. Empty enumeration (``pyserial`` missing,
    no devices) collapses to skip without raising, mirroring the
    extension's empty-list handling.
    """
    ports = list_serial_ports()
    if auto_detected is not None:
        options: list[tuple[str, str]] = [
            ("__use__", f"Use {auto_detected} (auto-detected)"),
        ]
        if ports:
            options.append(("__pick__", "Pick a different port"))
        options.append(("__skip__", "Skip — keep any existing saved port"))
        choice = _choose(
            "How should the ring's serial port be configured?",
            tuple(options),
            default="__use__",
        )
        if choice == "__use__":
            return auto_detected
        if choice == "__skip__":
            return None
    else:
        if not ports:
            print(
                "No matching serial device detected and no ports could be enumerated."
            )
            return None
        options = [
            ("__pick__", "Pick a port from the list"),
            ("__skip__", "Skip — keep any existing saved port"),
        ]
        choice = _choose(
            "How should the ring's serial port be configured?",
            tuple(options),
            default="__skip__",
        )
        if choice == "__skip__":
            return None

    if not ports:
        print("No serial ports could be enumerated. Skipping.")
        return None
    port_options = tuple(
        (
            entry["device"],
            f"{entry['device']} — {entry['description']}".rstrip(" —"),
        )
        for entry in ports
    )
    return _choose(
        "Which serial port should the ring use?",
        port_options,
        default=port_options[0][0],
    )


def prompt_for_selections() -> WizardSelections:
    """Collect setup choices from a terminal user."""
    scope_label = _choose(
        "Where should the ring work?",
        (
            (SCOPE_GLOBAL, "All repositories (recommended)"),
            (SCOPE_REPO, "One repository only"),
        ),
        default=SCOPE_GLOBAL,
    )
    repo_path = None
    if scope_label == SCOPE_REPO:
        repo_path = Path(input("Target repository path: ").strip()).expanduser()

    board_options = tuple((board.id, board.name) for board in list_boards())
    board_id = _choose("Which board are you using?", board_options, default=board_options[0][0])
    board = get_board(board_id)
    runtime_default = default_runtime(board.id).runtime
    runtime_options = tuple((runtime.runtime, runtime.label) for runtime in board.runtimes)
    runtime = _choose(
        "Which firmware runtime do you want?",
        runtime_options,
        default=runtime_default,
    )
    runtime_meta = get_runtime(board.id, runtime)

    pin_prompt = "Data pin"
    if runtime_meta.default_pin:
        pin_prompt += f" [{runtime_meta.default_pin}]"
    data_pin = input(f"{pin_prompt}: ").strip() or runtime_meta.default_pin

    pixel_choice = _choose(
        "Which ring size do you have?",
        (
            ("24", "24 LEDs — Adafruit NeoPixel Ring 24 (product 1586)"),
            ("16", "16 LEDs — Adafruit NeoPixel Ring 16 (product 1463)"),
            ("12", "12 LEDs — Adafruit NeoPixel Ring 12 (product 1643)"),
        ),
        default=str(DEFAULT_PIXEL_COUNT),
    )
    pixel_count = int(pixel_choice)

    auto_detect = _confirm("Attempt host USB serial auto-detection?", default=True)
    serial_port: str | None = None
    firmware_target = None
    approve = False
    if auto_detect:
        auto_detected = detect_serial_port(Config())
        serial_port = _pick_serial_port_interactively(auto_detected=auto_detected)
        if serial_port is not None:
            approve = _confirm(
                f"Approve firmware install/copy for {serial_port}?",
                default=False,
            )
            if approve and runtime == RUNTIME_CIRCUITPYTHON:
                drive = find_circuitpython_drive()
                default_target = str(drive) if drive is not None else ""
                target_text = (
                    input(f"CIRCUITPY path [{default_target}]: ").strip()
                    or default_target
                )
                if target_text:
                    firmware_target = Path(target_text).expanduser()
        elif auto_detected is None:
            print(
                "No serial port chosen; firmware install/copy will be skipped."
            )

    return WizardSelections(
        scope=scope_label,
        repo_path=repo_path,
        board_id=board.id,
        runtime=runtime,
        data_pin=data_pin,
        auto_detect_port=auto_detect,
        approve_firmware=approve,
        firmware_target=firmware_target,
        force_hooks=True,
        pixel_count=pixel_count,
        serial_port=serial_port,
    )


def _read_json_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add setup-status-ring arguments to *parser*."""
    parser.add_argument(
        "--options-json",
        action="store_true",
        help="Print board/runtime options as JSON and exit",
    )
    parser.add_argument(
        "--detect-port-json",
        action="store_true",
        help="Print host serial auto-detection result as JSON and exit",
    )
    parser.add_argument(
        "--detect-circuitpy-json",
        action="store_true",
        help="Print CIRCUITPY drive auto-detection result as JSON and exit",
    )
    parser.add_argument(
        "--list-ports-json",
        action="store_true",
        help="Print every enumerable serial port as JSON and exit",
    )
    parser.add_argument(
        "--from-json",
        metavar="PATH|-",
        help="Read wizard selections from JSON instead of prompting",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the setup plan as JSON without executing it",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Execute without a final confirmation prompt",
    )
    parser.add_argument(
        "--venv-dir",
        help=(
            "Override the dedicated setup virtual environment path "
            "(defaults to <repo>/.venv when run from a copilot-status-ring "
            "checkout, else a user-level path under the platform state dir)"
        ),
    )
    parser.add_argument(
        "--package-spec",
        default=None,
        help=(
            "Package spec to install into the setup venv "
            "(defaults to the local clone path when run from a copilot-status-ring "
            "checkout, else the GitHub URL)"
        ),
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help=argparse.SUPPRESS,
    )


def _format_summary(
    result: SetupResult,
    *,
    pixel_count: int,
    scope: str,
    approve_firmware: bool,
    chosen_port: str | None = None,
) -> list[str]:
    """Render the post-setup summary as a list of stderr-ready lines.

    Extracted from ``run_setup_status_ring_from_args`` so the structured
    block stays unit-testable and easy to tweak without touching argparse
    plumbing. Returns blank-line-separated lines in display order.

    ``chosen_port`` is the value of ``WizardSelections.serial_port`` (the
    port the user explicitly picked or kept). When it matches
    ``result.detected_port`` the row is labeled "chosen" rather than
    "auto-detected", so the tail honestly reflects the user's decision.
    """
    rows: list[tuple[str, str]] = []
    rows.append(("Venv", str(result.plan.venv_dir)))
    rows.append(("Scope", scope))
    rows.append(("Ring size", f"{pixel_count} LEDs"))
    if result.detected_port:
        if chosen_port is not None and chosen_port == result.detected_port:
            suffix = "chosen"
        else:
            suffix = "auto-detected"
        rows.append(("Serial port", f"{result.detected_port} ({suffix})"))
    if result.firmware_written:
        files_label = ", ".join(path.name for path in result.firmware_written)
        rows.append(("Firmware copied", files_label))
    elif result.firmware_prepared_dir is not None:
        rows.append(("Firmware prepared", str(result.firmware_prepared_dir)))
    elif approve_firmware:
        rows.append(("Firmware", "prepared (follow manual runtime steps)"))
    if result.config_written is not None:
        rows.append(("Config", str(result.config_written)))

    label_width = max(len(label) for label, _ in rows)
    lines = ["Setup complete."]
    for label, value in rows:
        lines.append(f"  {label.ljust(label_width)}  {value}")
    for warning in result.firmware_warnings:
        lines.append(f"  Warning: {warning}")
    return lines


def run_setup_status_ring_from_args(args: argparse.Namespace) -> bool:
    """Run the setup-status-ring command from parsed argparse arguments."""
    try:
        if args.options_json:
            print(json.dumps(options_payload(), indent=2))
            return True
        if args.detect_port_json:
            print(json.dumps(detect_port_payload(), indent=2))
            return True
        if args.detect_circuitpy_json:
            print(json.dumps(detect_circuitpy_payload(), indent=2))
            return True
        if args.list_ports_json:
            print(json.dumps(list_ports_payload(), indent=2))
            return True

        selections = (
            selections_from_json(_read_json_input(args.from_json))
            if args.from_json
            else prompt_for_selections()
        )
        venv_dir = Path(args.venv_dir).expanduser() if args.venv_dir else None
        plan = build_setup_plan(
            selections,
            venv_dir=venv_dir,
            package_spec=args.package_spec,
        )
        if args.plan_only:
            print(json.dumps(plan.to_dict(), indent=2))
            return True

        if not args.yes and not _confirm("Proceed with setup?", default=True):
            print("Aborted.", file=sys.stderr)
            return False

        result = execute_setup_plan(plan, skip_install=args.skip_install)
        summary = _format_summary(
            result,
            pixel_count=selections.pixel_count,
            scope=selections.scope,
            approve_firmware=selections.approve_firmware,
            chosen_port=selections.serial_port,
        )
        print("", file=sys.stderr)
        for line in summary:
            print(line, file=sys.stderr)
        return True
    except (KeyError, OSError, subprocess.CalledProcessError, FirmwareInstallError) as exc:
        print(f"setup-status-ring: {exc}", file=sys.stderr)
        return False
    except SetupWizardError as exc:
        print(f"setup-status-ring: {exc}", file=sys.stderr)
        return False
