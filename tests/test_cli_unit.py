# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Unit tests for cli.main — in-process with mocked subcommand targets."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from copilot_command_ring.cli import main


class TestCLISetup:
    """The ``setup`` subcommand delegates to setup_global_hooks."""

    @patch("copilot_command_ring.deploy.setup_global_hooks", return_value=True)
    def test_setup_calls_setup_global_hooks(self, mock_setup: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["setup"])
        assert exc_info.value.code == 0
        mock_setup.assert_called_once_with(force=False)

    @patch("copilot_command_ring.deploy.setup_global_hooks", return_value=True)
    def test_setup_force_flag(self, mock_setup: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["setup", "--force"])
        assert exc_info.value.code == 0
        mock_setup.assert_called_once_with(force=True)

    @patch("copilot_command_ring.deploy.setup_global_hooks", return_value=False)
    def test_setup_returns_exit_1_on_failure(self, mock_setup: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["setup"])
        assert exc_info.value.code == 1
        mock_setup.assert_called_once_with(force=False)


class TestCLIDeploy:
    """The ``deploy`` subcommand delegates to deploy_hooks."""

    @patch("copilot_command_ring.deploy.deploy_hooks", return_value=True)
    def test_deploy_calls_deploy_hooks(self, mock_deploy: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["deploy", "/some/path"])
        assert exc_info.value.code == 0
        mock_deploy.assert_called_once_with("/some/path", force=False)

    @patch("copilot_command_ring.deploy.deploy_hooks", return_value=True)
    def test_deploy_force_flag(self, mock_deploy: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["deploy", "/some/path", "--force"])
        assert exc_info.value.code == 0
        mock_deploy.assert_called_once_with("/some/path", force=True)

    @patch("copilot_command_ring.deploy.deploy_hooks", return_value=False)
    def test_deploy_returns_exit_1_on_failure(self, mock_deploy: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["deploy", "/some/path"])
        assert exc_info.value.code == 1
        mock_deploy.assert_called_once_with("/some/path", force=False)


class TestCLIHook:
    """The ``hook`` subcommand rewrites sys.argv and calls hook_main."""

    @patch("copilot_command_ring.hook_main.main")
    def test_hook_calls_hook_main(self, mock_hook: MagicMock) -> None:
        main(["hook", "sessionStart"])
        mock_hook.assert_called_once()

    @patch("copilot_command_ring.hook_main.main")
    def test_hook_rewrites_sys_argv(self, mock_hook: MagicMock) -> None:
        import sys

        main(["hook", "preToolUse"])
        assert sys.argv == ["copilot-command-ring", "preToolUse"]


class TestCLISetupStatusRing:
    """The guided setup subcommand delegates to setup_wizard."""

    @patch("copilot_command_ring.setup_wizard.run_setup_status_ring_from_args", return_value=True)
    def test_setup_status_ring_calls_wizard(self, mock_wizard: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["setup-status-ring", "--options-json"])
        assert exc_info.value.code == 0
        mock_wizard.assert_called_once()

    @patch("copilot_command_ring.setup_wizard.run_setup_status_ring_from_args", return_value=False)
    def test_setup_status_ring_returns_exit_1_on_failure(self, mock_wizard: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["setup-status-ring", "--options-json"])
        assert exc_info.value.code == 1
        mock_wizard.assert_called_once()

    @patch("copilot_command_ring.setup_wizard.run_setup_status_ring_from_args", return_value=True)
    def test_wizard_alias_calls_setup_status_ring(self, mock_wizard: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["wizard", "--options-json"])
        assert exc_info.value.code == 0
        mock_wizard.assert_called_once()


class TestCLINoCommand:
    """No subcommand prints help and exits 0."""

    def test_no_command_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0


class TestCLIDoctor:
    """The ``doctor`` subcommand delegates to doctor.run_doctor."""

    @patch("copilot_command_ring.doctor.run_doctor", return_value=0)
    def test_doctor_default_invokes_with_ping(self, mock_run: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["doctor"])
        assert exc_info.value.code == 0
        mock_run.assert_called_once_with(config_dir=None, ping=True)

    @patch("copilot_command_ring.doctor.run_doctor", return_value=0)
    def test_doctor_no_ping_flag(self, mock_run: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["doctor", "--no-ping"])
        assert exc_info.value.code == 0
        mock_run.assert_called_once_with(config_dir=None, ping=False)

    @patch("copilot_command_ring.doctor.run_doctor", return_value=0)
    def test_doctor_config_dir_passthrough(self, mock_run: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["doctor", "--config-dir", "/tmp/foo"])
        assert exc_info.value.code == 0
        # Use Path equality so the test passes on Windows and POSIX.
        from pathlib import Path

        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["config_dir"] == Path("/tmp/foo")
        assert call_kwargs["ping"] is True

    @patch("copilot_command_ring.doctor.run_doctor", return_value=1)
    def test_doctor_propagates_failure_exit_code(self, mock_run: MagicMock) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["doctor"])
        assert exc_info.value.code == 1
        mock_run.assert_called_once()
