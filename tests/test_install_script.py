# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for the macOS/Linux install.sh bootstrapper."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="install.sh targets macOS/Linux")


def _install_env(tmp_path: Path, *, path: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")
    env["COPILOT_HOME"] = str(tmp_path / "copilot")
    if path is not None:
        env["PATH"] = path
    return env


def _run_install(
    args: list[str],
    tmp_path: Path,
    *,
    path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        env=_install_env(tmp_path, path=path),
    )


def test_help_output_documents_bootstrap() -> None:
    result = subprocess.run(
        ["bash", str(INSTALL_SH), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Bootstrap Copilot Command Ring" in result.stdout
    assert "--firmware-target PATH" in result.stdout


def test_dry_run_default_plan_uses_pico_circuitpython(tmp_path: Path) -> None:
    result = _run_install(
        ["--dry-run", "--yes", "--no-detect-port", "--venv-dir", str(tmp_path / "venv")],
        tmp_path,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert '"scope": "global"' in output
    assert '"board_id": "raspberry-pi-pico"' in output
    assert '"runtime": "circuitpython"' in output
    assert '"data_pin": "board.GP6"' in output
    assert '"auto_detect_port": false' in output
    assert '"approve_firmware": true' in output
    assert str(tmp_path / "venv") in output


def test_dry_run_repo_scope_and_firmware_target(tmp_path: Path) -> None:
    repo = tmp_path / "target-repo"
    repo.mkdir()
    circuitpy = tmp_path / "CIRCUITPY"
    circuitpy.mkdir()

    result = _run_install(
        [
            "--dry-run",
            "--yes",
            "--repo",
            str(repo),
            "--firmware-target",
            str(circuitpy),
            "--venv-dir",
            str(tmp_path / "venv"),
        ],
        tmp_path,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert '"scope": "repo"' in output
    assert f'"repo_path": "{repo}"' in output
    assert f'"firmware_target": "{circuitpy}"' in output


def test_script_requires_full_repo_checkout(tmp_path: Path) -> None:
    copied = tmp_path / "install.sh"
    copied.write_text(INSTALL_SH.read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        ["bash", str(copied), "--dry-run", "--yes"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
        env=_install_env(tmp_path),
    )
    output = result.stdout + result.stderr

    assert result.returncode == 1
    assert "full copilot-status-ring clone" in output


def test_python_version_failure_is_actionable(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"-\" ]]; then exit 1; fi\n"
        "echo 'Python 3.8.0'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    (fake_bin / "python").symlink_to(fake_python)
    path = f"{fake_bin}:/usr/bin:/bin"

    result = _run_install(["--dry-run", "--yes"], tmp_path, path=path)
    output = result.stdout + result.stderr

    assert result.returncode == 1
    assert "Python 3.9+ is required" in output
