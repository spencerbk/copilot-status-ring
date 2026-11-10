# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Package-archive checks for the Copilot App extension assets."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


def test_wheel_contains_app_extension_assets(tmp_path: Path) -> None:
    """Include both App extension assets in the built wheel."""
    repo_root = Path(__file__).resolve().parent.parent
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(tmp_path),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    wheel = next(tmp_path.glob("*.whl"))

    with ZipFile(wheel) as archive:
        names = set(archive.namelist())

    assert {
        "copilot_command_ring/copilot_app_extension/extension.mjs",
        "copilot_command_ring/copilot_app_extension/bridge.mjs",
    } <= names
