# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for copilot_command_ring.deploy and copilot_command_ring.cli."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from copilot_command_ring.deploy import (
    _build_global_hook_json,
    _copilot_hooks_dir,
    _render_hook_ps1,
    _render_hook_sh,
    deploy_hooks,
    setup_global_hooks,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST_DIR = REPO_ROOT / "host"


class TestDeployHooks:
    """Unit tests for the deploy_hooks function."""

    def test_creates_hooks_directory(self, tmp_path: Path) -> None:
        result = deploy_hooks(tmp_path)
        assert result is True
        hooks_dir = tmp_path / ".github" / "hooks"
        assert hooks_dir.is_dir()

    def test_writes_all_hook_files(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        hooks_dir = tmp_path / ".github" / "hooks"
        assert (hooks_dir / "copilot-command-ring.json").is_file()
        assert (hooks_dir / "run-hook.ps1").is_file()
        assert (hooks_dir / "run-hook.sh").is_file()

    def test_json_contains_all_events(self, tmp_path: Path) -> None:
        import json

        deploy_hooks(tmp_path)
        data = json.loads(
            (tmp_path / ".github" / "hooks" / "copilot-command-ring.json").read_text()
        )
        expected_events = {
            "sessionStart",
            "sessionEnd",
            "userPromptSubmitted",
            "preToolUse",
            "postToolUse",
            "postToolUseFailure",
            "permissionRequest",
            "subagentStart",
            "subagentStop",
            "agentStop",
            "preCompact",
            "errorOccurred",
            "notification",
        }
        assert set(data["hooks"].keys()) == expected_events

    def test_ps1_references_console_script(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        content = (tmp_path / ".github" / "hooks" / "run-hook.ps1").read_text()
        # Fallback chain still references the console script
        assert "copilot-command-ring" in content
        assert "hook" in content

    def test_sh_references_console_script(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        content = (tmp_path / ".github" / "hooks" / "run-hook.sh").read_text()
        assert "copilot-command-ring hook" in content

    def test_sh_has_ppid_session_id(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        content = (tmp_path / ".github" / "hooks" / "run-hook.sh").read_text()
        assert "COPILOT_RING_CLI_PID" in content

    def test_ps1_has_session_id(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        content = (tmp_path / ".github" / "hooks" / "run-hook.ps1").read_text()
        assert "COPILOT_RING_CLI_PID" in content

    def test_refuses_overwrite_noninteractive(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        result = deploy_hooks(tmp_path, interactive=False)
        assert result is False

    def test_force_overwrites(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        result = deploy_hooks(tmp_path, force=True)
        assert result is True

    def test_interactive_overwrite_accepted(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        with patch("builtins.input", return_value="y"):
            result = deploy_hooks(tmp_path, interactive=True)
        assert result is True

    def test_interactive_overwrite_declined(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        with patch("builtins.input", return_value="n"):
            result = deploy_hooks(tmp_path, interactive=True)
        assert result is False

    def test_nonexistent_target_returns_false(self, tmp_path: Path) -> None:
        result = deploy_hooks(tmp_path / "does_not_exist")
        assert result is False

    def test_idempotent_with_force(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        deploy_hooks(tmp_path, force=True)
        hooks_dir = tmp_path / ".github" / "hooks"
        assert (hooks_dir / "copilot-command-ring.json").is_file()

    def test_ps1_embeds_python_path(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        content = (tmp_path / ".github" / "hooks" / "run-hook.ps1").read_text()
        resolved = str(Path(sys.executable).resolve())
        assert resolved in content
        assert "Test-Path" in content

    def test_sh_embeds_python_path(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        content = (tmp_path / ".github" / "hooks" / "run-hook.sh").read_text()
        resolved = str(Path(sys.executable).resolve())
        assert resolved in content

    def test_ps1_warns_when_no_runner(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        content = (tmp_path / ".github" / "hooks" / "run-hook.ps1").read_text()
        assert "no runner found" in content
        assert "rerun setup/deploy" in content

    def test_sh_warns_when_no_runner(self, tmp_path: Path) -> None:
        deploy_hooks(tmp_path)
        content = (tmp_path / ".github" / "hooks" / "run-hook.sh").read_text()
        assert "no runner found" in content
        assert "rerun setup/deploy" in content


class TestRenderHookScripts:
    """Unit tests for the hook script rendering functions."""

    def test_ps1_escapes_apostrophes(self) -> None:
        result = _render_hook_ps1(r"C:\Users\O'Brien\.venv\Scripts\python.exe")
        assert "O''Brien" in result

    def test_ps1_handles_spaces_in_path(self) -> None:
        result = _render_hook_ps1(r"C:\Program Files\Python312\python.exe")
        assert r"C:\Program Files\Python312\python.exe" in result

    def test_sh_quotes_path_with_spaces(self) -> None:
        result = _render_hook_sh("/home/user/my project/.venv/bin/python")
        assert "my project" in result
        # shlex.quote wraps in single quotes
        assert "'/home/user/my project/.venv/bin/python'" in result

    def test_sh_quotes_path_with_apostrophes(self) -> None:
        python_path = "/home/o'brien/.venv/bin/python"
        result = _render_hook_sh(python_path)
        assert shlex.quote(python_path) in result

    def test_ps1_preserves_fallback_chain(self) -> None:
        result = _render_hook_ps1("/usr/bin/python3")
        assert "copilot-command-ring" in result
        assert "'py'" in result
        assert "'python'" in result

    def test_sh_preserves_fallback_chain(self) -> None:
        result = _render_hook_sh("/usr/bin/python3")
        assert "copilot-command-ring hook" in result
        assert "python3 -m" in result
        assert "python -m" in result


class TestSetupGlobalHooks:
    """Unit tests for the setup_global_hooks function."""

    def test_copilot_hooks_dir_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COPILOT_HOME", raising=False)
        result = _copilot_hooks_dir()
        assert result == Path.home() / ".copilot" / "hooks"

    def test_copilot_hooks_dir_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COPILOT_HOME", "/custom/copilot")
        result = _copilot_hooks_dir()
        assert result == Path("/custom/copilot/hooks")

    def test_creates_hooks_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        result = setup_global_hooks(force=True)
        assert result is True
        assert (copilot_home / "hooks").is_dir()

    def test_writes_all_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        setup_global_hooks(force=True)
        hooks_dir = copilot_home / "hooks"
        assert (hooks_dir / "copilot-command-ring.json").is_file()
        assert (hooks_dir / "run-hook.ps1").is_file()
        assert (hooks_dir / "run-hook.sh").is_file()

    def test_json_contains_all_events(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import json

        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        setup_global_hooks(force=True)
        data = json.loads(
            (copilot_home / "hooks" / "copilot-command-ring.json").read_text()
        )
        expected_events = {
            "sessionStart", "sessionEnd", "userPromptSubmitted",
            "preToolUse", "postToolUse", "postToolUseFailure",
            "permissionRequest", "subagentStart", "subagentStop",
            "agentStop", "preCompact", "errorOccurred", "notification",
        }
        assert set(data["hooks"].keys()) == expected_events

    def test_json_uses_absolute_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import json

        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        setup_global_hooks(force=True)
        data = json.loads(
            (copilot_home / "hooks" / "copilot-command-ring.json").read_text()
        )
        hook_entry = data["hooks"]["sessionStart"][0]
        # Global hooks use absolute paths, not relative .github/hooks/
        assert ".github" not in hook_entry["powershell"]
        assert ".github" not in hook_entry["bash"]
        assert "run-hook.ps1" in hook_entry["powershell"]
        assert "run-hook.sh" in hook_entry["bash"]

    def test_build_global_hook_json_has_absolute_paths(self, tmp_path: Path) -> None:
        import json

        hooks_dir = tmp_path / "hooks"
        result = _build_global_hook_json(hooks_dir)
        data = json.loads(result)
        ps_cmd = data["hooks"]["preToolUse"][0]["powershell"]
        bash_cmd = data["hooks"]["preToolUse"][0]["bash"]
        # PowerShell uses & 'path' syntax for safe invocation
        assert ps_cmd.startswith("& '")
        assert str(hooks_dir / "run-hook.ps1") in ps_cmd
        # Bash uses quoted path
        assert "run-hook.sh" in bash_cmd

    def test_build_global_hook_json_escapes_single_quotes_in_paths(self) -> None:
        import json

        hooks_dir = Path(r"C:\Users\O'Brien\.copilot\hooks")
        result = _build_global_hook_json(hooks_dir)
        data = json.loads(result)
        ps_cmd = data["hooks"]["sessionStart"][0]["powershell"]
        bash_cmd = data["hooks"]["sessionStart"][0]["bash"]
        assert "O''Brien" in ps_cmd
        assert "'\"'\"'" in bash_cmd

    def test_refuses_overwrite_noninteractive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        setup_global_hooks(force=True)
        result = setup_global_hooks(interactive=False)
        assert result is False

    def test_force_overwrites(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        setup_global_hooks(force=True)
        result = setup_global_hooks(force=True)
        assert result is True

    def test_interactive_overwrite_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        setup_global_hooks(force=True)
        with patch("builtins.input", return_value="y"):
            result = setup_global_hooks(interactive=True)
        assert result is True

    def test_interactive_overwrite_declined(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        setup_global_hooks(force=True)
        with patch("builtins.input", return_value="n"):
            result = setup_global_hooks(interactive=True)
        assert result is False

    def test_ps1_embeds_python_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        setup_global_hooks(force=True)
        content = (copilot_home / "hooks" / "run-hook.ps1").read_text()
        resolved = str(Path(sys.executable).resolve())
        assert resolved in content

    def test_sh_embeds_python_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        copilot_home = tmp_path / "copilot"
        monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
        setup_global_hooks(force=True)
        content = (copilot_home / "hooks" / "run-hook.sh").read_text()
        resolved = str(Path(sys.executable).resolve())
        assert resolved in content


class TestCLI:
    """Tests for the copilot-command-ring CLI entry point."""

    def _cli_env(self, **extra: str) -> dict[str, str]:
        """Return a minimal env dict with PYTHONPATH pointing at host/."""
        import os

        env = {
            "PYTHONPATH": str(HOST_DIR),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        }
        env.update(extra)
        return env

    def test_deploy_subcommand(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "copilot_command_ring.cli", "deploy", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=10,
            env=self._cli_env(),
        )
        assert result.returncode == 0
        assert (tmp_path / ".github" / "hooks" / "copilot-command-ring.json").is_file()

    def test_hook_subcommand_dry_run(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "copilot_command_ring.cli", "hook", "sessionStart"],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            env=self._cli_env(COPILOT_RING_DRY_RUN="1"),
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_no_subcommand_shows_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "copilot_command_ring.cli"],
            capture_output=True,
            text=True,
            timeout=10,
            env=self._cli_env(),
        )
        assert result.returncode == 0

    def test_deploy_nonexistent_target(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "copilot_command_ring.cli",
                "deploy",
                str(tmp_path / "nope"),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=self._cli_env(),
        )
        assert result.returncode == 1

    def test_setup_subcommand(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "copilot_command_ring.cli",
                "setup", "--force",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=self._cli_env(COPILOT_HOME=str(tmp_path)),
        )
        assert result.returncode == 0
        assert (tmp_path / "hooks" / "copilot-command-ring.json").is_file()
