# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Unit tests for the doctor diagnostic command."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from copilot_command_ring import doctor
from copilot_command_ring.config import Config, ConfigMetadata


@dataclass
class _FakePort:
    """Stand-in for pyserial's ListPortInfo with the attrs the doctor reads."""

    device: str
    description: str
    hwid: str = ""
    location: str | None = None


def _config(**overrides: object) -> Config:
    defaults: dict[str, object] = {
        "serial_port": None,
        "baud": 115200,
        "pixel_count": 24,
        "brightness": 0.04,
        "idle_mode": "breathing",
        "dry_run": False,
        "lock_timeout": 1.0,
        "device_match_descriptions": ["Copilot Command Ring", "USB Serial"],
    }
    defaults.update(overrides)
    return Config(**defaults)  # type: ignore[arg-type]


def _meta(**overrides: object) -> ConfigMetadata:
    defaults: dict[str, object] = {"config_path": None, "parse_error": None}
    defaults.update(overrides)
    return ConfigMetadata(**defaults)  # type: ignore[arg-type]


def _run(
    *,
    config: Config | None = None,
    meta: ConfigMetadata | None = None,
    ports: list[_FakePort] | None = None,
    ping_result: bool = True,
    lock_acquires: bool = True,
    lock_stamp: tuple[int, float] | None = None,
    pyserial_available: bool = True,
    no_ping: bool = False,
) -> tuple[int, str]:
    """Drive run_doctor with mocked dependencies; return (exit_code, stdout)."""
    config = config or _config()
    meta = meta or _meta()
    ports = ports if ports is not None else []

    fake_serial_module = MagicMock() if pyserial_available else None
    fake_comports = MagicMock(return_value=ports)

    fake_lock_cm = MagicMock()
    fake_lock_cm.__enter__ = MagicMock(return_value=lock_acquires)
    fake_lock_cm.__exit__ = MagicMock(return_value=False)
    fake_serial_lock_cls = MagicMock(return_value=fake_lock_cm)

    fake_send_event = MagicMock(return_value=ping_result)
    fake_load = MagicMock(return_value=(config, meta))

    stream = io.StringIO()

    patches: list = [
        patch("copilot_command_ring.doctor.load_config_with_metadata", fake_load),
        patch("copilot_command_ring.doctor.SerialLock", fake_serial_lock_cls),
        patch("copilot_command_ring.doctor.send_event", fake_send_event),
        patch(
            "copilot_command_ring.doctor._read_lock_stamp",
            return_value=lock_stamp,
        ),
    ]

    if pyserial_available:
        # _check_pyserial uses a local `import serial`. Patch sys.modules so the
        # import succeeds; _enumerate_ports does its own local import of
        # `serial.tools.list_ports` so patch that too.
        import sys

        patches.append(
            patch.dict(
                sys.modules,
                {
                    "serial": fake_serial_module,
                    "serial.tools": MagicMock(),
                    "serial.tools.list_ports": MagicMock(comports=fake_comports),
                },
            ),
        )
    else:
        # Force ImportError for `import serial`.
        import sys

        original_modules = {
            key: sys.modules[key]
            for key in ("serial", "serial.tools", "serial.tools.list_ports")
            if key in sys.modules
        }
        for key in original_modules:
            del sys.modules[key]

        def _block_serial_import(name: str, *args: object, **kwargs: object):
            if name == "serial" or name.startswith("serial."):
                raise ImportError(f"No module named {name!r}")
            return _orig_import(name, *args, **kwargs)

        import builtins

        _orig_import = builtins.__import__
        patches.append(patch("builtins.__import__", side_effect=_block_serial_import))

    try:
        for p in patches:
            p.start()
        exit_code = doctor.run_doctor(ping=not no_ping, stream=stream)
    finally:
        for p in reversed(patches):
            p.stop()
        if not pyserial_available:
            for key, mod in original_modules.items():
                sys.modules[key] = mod

    return exit_code, stream.getvalue()


# ── happy path ────────────────────────────────────────────────────────


class TestHappyPath:
    def test_all_ok_exits_zero(self) -> None:
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        exit_code, output = _run(ports=ports)
        assert exit_code == 0
        assert "RESULT: OK -- all checks passed" in output
        assert "[ OK ] Ping" in output
        assert "[ OK ] Match" in output

    def test_ping_uses_transient_notification_state(self) -> None:
        """Ping must NOT use sessionStart -- that is persistent and would
        leave the ring in a fake active state for up to the TTL."""
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        with patch("copilot_command_ring.doctor.send_event") as mock_send:
            mock_send.return_value = True
            _run_with_send_capture(ports, mock_send)
        sent_message = mock_send.call_args.args[1]
        assert sent_message["event"] == "notification"
        assert sent_message["state"] == "notify"
        # state must NOT carry a TTL (transient)
        assert "ttl_s" not in sent_message


def _run_with_send_capture(ports: list[_FakePort], mock_send: MagicMock) -> None:
    """Helper for tests that patch send_event externally to inspect args."""
    config = _config()
    meta = _meta()
    fake_lock_cm = MagicMock()
    fake_lock_cm.__enter__ = MagicMock(return_value=True)
    fake_lock_cm.__exit__ = MagicMock(return_value=False)
    import sys

    extra = patch.dict(
        sys.modules,
        {
            "serial": MagicMock(),
            "serial.tools": MagicMock(),
            "serial.tools.list_ports": MagicMock(comports=MagicMock(return_value=ports)),
        },
    )
    extra.start()
    try:
        with (
            patch(
                "copilot_command_ring.doctor.load_config_with_metadata",
                return_value=(config, meta),
            ),
            patch("copilot_command_ring.doctor.SerialLock", return_value=fake_lock_cm),
        ):
            doctor.run_doctor(ping=True, stream=io.StringIO())
    finally:
        extra.stop()


# ── dry_run is a hard FAIL ───────────────────────────────────────────


class TestDryRunGuard:
    def test_dry_run_enabled_is_failure(self) -> None:
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        config = _config(dry_run=True)
        exit_code, output = _run(config=config, ports=ports)
        assert exit_code == 1
        assert "[FAIL] Dry-run" in output
        assert "RESULT: FAIL" in output

    def test_dry_run_skips_ping(self) -> None:
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        config = _config(dry_run=True)
        _, output = _run(config=config, ports=ports)
        assert "Ping: skipped (upstream check failed)" in output


# ── pyserial missing ─────────────────────────────────────────────────


class TestPyserialMissing:
    def test_missing_pyserial_is_failure(self) -> None:
        exit_code, output = _run(pyserial_available=False)
        assert exit_code == 1
        assert "[FAIL] pyserial" in output
        assert "pip install pyserial" in output

    def test_missing_pyserial_skips_downstream_checks(self) -> None:
        _, output = _run(pyserial_available=False)
        assert "Ports: skipped (pyserial unavailable)" in output
        assert "Match: skipped (pyserial unavailable)" in output
        assert "Lock: skipped (pyserial unavailable)" in output


# ── port discovery + matching ────────────────────────────────────────


class TestPortMatching:
    def test_no_ports_warns_and_match_fails(self) -> None:
        exit_code, output = _run(ports=[])
        assert exit_code == 1
        assert "[WARN] Ports" in output
        assert "[FAIL] Match" in output

    def test_no_descriptor_match_lists_descriptors_tried(self) -> None:
        ports = [_FakePort(device="COM3", description="Intel AMT - SOL")]
        exit_code, output = _run(ports=ports)
        assert exit_code == 1
        assert "[FAIL] Match" in output
        assert "tried:" in output
        assert "USB Serial" in output

    def test_explicit_port_present_in_enumeration_passes(self) -> None:
        config = _config(serial_port="COM7")
        ports = [
            _FakePort(device="COM3", description="Intel AMT - SOL"),
            _FakePort(device="COM7", description="some other description"),
        ]
        exit_code, output = _run(config=config, ports=ports)
        assert exit_code == 0
        assert "[ OK ] Match" in output
        assert "'COM7'" in output

    def test_explicit_port_absent_from_enumeration_fails(self) -> None:
        """Critical bug class: stale config + --no-ping must NOT false-clear."""
        config = _config(serial_port="COM99")
        ports = [_FakePort(device="COM3", description="Intel AMT - SOL")]
        exit_code, output = _run(config=config, ports=ports, no_ping=True)
        assert exit_code == 1
        assert "[FAIL] Match" in output
        assert "NOT in enumeration" in output


# ── lock state ───────────────────────────────────────────────────────


class TestLockState:
    def test_lock_held_is_warning_not_failure(self) -> None:
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        exit_code, output = _run(
            ports=ports,
            lock_acquires=False,
            lock_stamp=(99999, 0.0),
        )
        assert exit_code == 0  # lock-held is WARN, not FAIL
        assert "[WARN] Lock" in output
        assert "pid=99999" in output


# ── ping failure ─────────────────────────────────────────────────────


class TestPingFailure:
    def test_ping_failure_is_failure(self) -> None:
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        exit_code, output = _run(ports=ports, ping_result=False)
        assert exit_code == 1
        assert "[FAIL] Ping" in output

    def test_no_ping_skips_send_event(self) -> None:
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        config = _config()
        meta = _meta()
        fake_lock_cm = MagicMock()
        fake_lock_cm.__enter__ = MagicMock(return_value=True)
        fake_lock_cm.__exit__ = MagicMock(return_value=False)
        import sys

        with (
            patch.dict(
                sys.modules,
                {
                    "serial": MagicMock(),
                    "serial.tools": MagicMock(),
                    "serial.tools.list_ports": MagicMock(
                        comports=MagicMock(return_value=ports),
                    ),
                },
            ),
            patch(
                "copilot_command_ring.doctor.load_config_with_metadata",
                return_value=(config, meta),
            ),
            patch("copilot_command_ring.doctor.SerialLock", return_value=fake_lock_cm),
            patch("copilot_command_ring.doctor.send_event") as mock_send,
        ):
            exit_code = doctor.run_doctor(ping=False, stream=io.StringIO())

        assert exit_code == 0
        mock_send.assert_not_called()


# ── config provenance ────────────────────────────────────────────────


class TestConfigReporting:
    def test_loaded_path_is_reported(self) -> None:
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        meta = _meta(config_path=Path("/tmp/.copilot-command-ring.local.json"))
        _, output = _run(ports=ports, meta=meta)
        assert "loaded from" in output
        assert "copilot-command-ring.local.json" in output

    def test_parse_error_is_warning(self) -> None:
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        meta = _meta(
            config_path=Path("/tmp/.copilot-command-ring.local.json"),
            parse_error="JSONDecodeError: Expecting value",
        )
        exit_code, output = _run(ports=ports, meta=meta)
        # parse error is WARN, not FAIL -- the doctor falls back to defaults
        assert exit_code == 0
        assert "[WARN] Config" in output
        assert "JSONDecodeError" in output


# ── load_config_with_metadata integration ────────────────────────────


class TestLoadConfigWithMetadata:
    """The new public API used by doctor."""

    def test_no_file_returns_none_path(self, tmp_path: Path) -> None:
        from copilot_command_ring.config import load_config_with_metadata

        cfg, meta = load_config_with_metadata(tmp_path)
        assert meta.config_path is None
        assert meta.parse_error is None
        assert cfg.serial_port is None

    def test_loaded_file_reports_path(self, tmp_path: Path) -> None:
        from copilot_command_ring.config import load_config_with_metadata

        config_file = tmp_path / ".copilot-command-ring.local.json"
        config_file.write_text(json.dumps({"serial_port": "COM5"}), encoding="utf-8")

        cfg, meta = load_config_with_metadata(tmp_path)
        assert meta.config_path == config_file
        assert meta.parse_error is None
        assert cfg.serial_port == "COM5"

    def test_invalid_json_reports_parse_error(self, tmp_path: Path) -> None:
        from copilot_command_ring.config import load_config_with_metadata

        config_file = tmp_path / ".copilot-command-ring.local.json"
        config_file.write_text("{not valid json", encoding="utf-8")

        cfg, meta = load_config_with_metadata(tmp_path)
        assert meta.config_path == config_file
        assert meta.parse_error is not None
        assert "JSONDecodeError" in meta.parse_error
        # falls back to defaults
        assert cfg.serial_port is None

    def test_non_object_json_reports_parse_error(self, tmp_path: Path) -> None:
        from copilot_command_ring.config import load_config_with_metadata

        config_file = tmp_path / ".copilot-command-ring.local.json"
        config_file.write_text("[1, 2, 3]", encoding="utf-8")

        cfg, meta = load_config_with_metadata(tmp_path)
        assert meta.config_path == config_file
        assert meta.parse_error is not None
        assert "JSON object" in meta.parse_error


# ── output sanity ────────────────────────────────────────────────────


class TestOutputSanity:
    def test_output_is_ascii(self) -> None:
        """Windows consoles can render the wrong code page; keep output ASCII."""
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        _, output = _run(ports=ports)
        for ch in output:
            assert ord(ch) < 128, f"non-ASCII char {ch!r} (U+{ord(ch):04X}) in output"

    @pytest.mark.parametrize("ping", [True, False])
    def test_report_contains_section_markers(self, ping: bool) -> None:
        ports = [_FakePort(device="COM6", description="USB Serial Device (COM6)")]
        _, output = _run(ports=ports, no_ping=not ping)
        for label in ("Config:", "Dry-run:", "pyserial:", "Ports:", "Match:", "Lock:", "Ping:"):
            assert label in output
