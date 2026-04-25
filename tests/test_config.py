# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for copilot_command_ring.config (configuration loading)."""

from __future__ import annotations

import json

import pytest
from copilot_command_ring.config import Config, load_config
from copilot_command_ring.constants import (
    DEFAULT_BAUD,
    DEFAULT_BRIGHTNESS,
    DEFAULT_DESCRIPTION_CONTAINS,
    DEFAULT_IDLE_MODE,
    DEFAULT_LOCK_TIMEOUT,
    DEFAULT_PIXEL_COUNT,
    ENV_BAUD,
    ENV_BRIGHTNESS,
    ENV_DRY_RUN,
    ENV_LOCK_TIMEOUT,
    ENV_PIXEL_COUNT,
    ENV_PORT,
)

# ── Default values ────────────────────────────────────────────────────────


def test_default_config_baud():
    cfg = Config()
    assert cfg.baud == DEFAULT_BAUD


def test_default_config_brightness():
    cfg = Config()
    assert cfg.brightness == DEFAULT_BRIGHTNESS


def test_default_config_pixel_count():
    cfg = Config()
    assert cfg.pixel_count == DEFAULT_PIXEL_COUNT


def test_default_config_idle_mode():
    cfg = Config()
    assert cfg.idle_mode == DEFAULT_IDLE_MODE


def test_default_config_serial_port_is_none():
    cfg = Config()
    assert cfg.serial_port is None


def test_default_config_dry_run_is_false():
    cfg = Config()
    assert cfg.dry_run is False


def test_default_config_lock_timeout():
    cfg = Config()
    assert cfg.lock_timeout == DEFAULT_LOCK_TIMEOUT


def test_default_config_device_match_descriptions():
    cfg = Config()
    assert cfg.device_match_descriptions == list(DEFAULT_DESCRIPTION_CONTAINS)


# ── Config from JSON file ────────────────────────────────────────────────


def test_config_file_overrides_baud(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    monkeypatch.delenv(ENV_BAUD, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"baud": 9600}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.baud == 9600


def test_config_file_overrides_serial_port(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"serial_port": "/dev/ttyACM0"}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.serial_port == "/dev/ttyACM0"


def test_config_file_overrides_brightness(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_BRIGHTNESS, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"brightness": 0.5}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.brightness == pytest.approx(0.5)


def test_config_file_overrides_idle_mode(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"idle_mode": "off"}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.idle_mode == "off"


def test_invalid_idle_mode_normalizes_to_default(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"idle_mode": "breathe"}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.idle_mode == DEFAULT_IDLE_MODE


def test_breathing_idle_mode_accepted(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"idle_mode": "breathing"}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.idle_mode == "breathing"


def test_default_idle_mode_is_breathing():
    assert DEFAULT_IDLE_MODE == "breathing"


def test_config_file_overrides_lock_timeout(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_LOCK_TIMEOUT, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"lock_timeout": 2.5}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.lock_timeout == pytest.approx(2.5)


def test_config_file_overrides_pixel_count(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"pixel_count": 12}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.pixel_count == 12


def test_invalid_config_file_pixel_count_is_ignored(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PIXEL_COUNT, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"pixel_count": 0}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.pixel_count == DEFAULT_PIXEL_COUNT


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_invalid_config_file_brightness_is_ignored(value, tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_BRIGHTNESS, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"brightness": value}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.brightness == DEFAULT_BRIGHTNESS


def test_config_file_overrides_device_match(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    data = {"device_match": {"description_contains": ["Feather"]}}
    config_file.write_text(json.dumps(data), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.device_match_descriptions == ["Feather"]


# ── Env vars override file values ────────────────────────────────────────


def test_env_port_overrides_file(tmp_path, monkeypatch):
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"serial_port": "/dev/ttyACM0"}), encoding="utf-8")
    monkeypatch.setenv(ENV_PORT, "COM5")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.serial_port == "COM5"


def test_env_baud_overrides_file(tmp_path, monkeypatch):
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"baud": 9600}), encoding="utf-8")
    monkeypatch.setenv(ENV_BAUD, "57600")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.baud == 57600


def test_env_brightness_overrides_file(tmp_path, monkeypatch):
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"brightness": 0.1}), encoding="utf-8")
    monkeypatch.setenv(ENV_BRIGHTNESS, "0.75")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.brightness == pytest.approx(0.75)


def test_env_pixel_count_overrides_file(tmp_path, monkeypatch):
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"pixel_count": 12}), encoding="utf-8")
    monkeypatch.setenv(ENV_PIXEL_COUNT, "48")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.pixel_count == 48


def test_env_lock_timeout_overrides_file(tmp_path, monkeypatch):
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"lock_timeout": 1.0}), encoding="utf-8")
    monkeypatch.setenv(ENV_LOCK_TIMEOUT, "3.25")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.lock_timeout == pytest.approx(3.25)


# ── Invalid env values are ignored ───────────────────────────────────────


def test_invalid_env_baud_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BAUD, "not_a_number")
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"baud": 9600}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.baud == 9600


def test_invalid_env_brightness_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BRIGHTNESS, "bright")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.brightness == DEFAULT_BRIGHTNESS


@pytest.mark.parametrize("value", ["0", "-1", "many"])
def test_invalid_env_pixel_count_is_ignored(value: str, tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_PIXEL_COUNT, value)
    cfg = load_config(config_dir=tmp_path)
    assert cfg.pixel_count == DEFAULT_PIXEL_COUNT


@pytest.mark.parametrize("value", ["-0.1", "1.1"])
def test_out_of_range_env_brightness_is_ignored(value: str, tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_BRIGHTNESS, value)
    cfg = load_config(config_dir=tmp_path)
    assert cfg.brightness == DEFAULT_BRIGHTNESS


def test_invalid_env_lock_timeout_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_LOCK_TIMEOUT, "slow")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.lock_timeout == DEFAULT_LOCK_TIMEOUT


def test_negative_config_file_lock_timeout_is_ignored(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_LOCK_TIMEOUT, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text(json.dumps({"lock_timeout": -1}), encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.lock_timeout == DEFAULT_LOCK_TIMEOUT


def test_negative_env_lock_timeout_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_LOCK_TIMEOUT, "-1")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.lock_timeout == DEFAULT_LOCK_TIMEOUT


# ── Missing config file handled gracefully ────────────────────────────────


def test_missing_config_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    monkeypatch.delenv(ENV_BAUD, raising=False)
    monkeypatch.delenv(ENV_BRIGHTNESS, raising=False)
    monkeypatch.delenv(ENV_DRY_RUN, raising=False)
    cfg = load_config(config_dir=tmp_path)
    assert cfg.baud == DEFAULT_BAUD
    assert cfg.serial_port is None


def test_malformed_json_config_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    monkeypatch.delenv(ENV_BAUD, raising=False)
    monkeypatch.delenv(ENV_BRIGHTNESS, raising=False)
    monkeypatch.delenv(ENV_DRY_RUN, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text("{{invalid json", encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.baud == DEFAULT_BAUD


def test_non_dict_json_config_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_PORT, raising=False)
    monkeypatch.delenv(ENV_BAUD, raising=False)
    config_file = tmp_path / ".copilot-command-ring.local.json"
    config_file.write_text("[1, 2, 3]", encoding="utf-8")
    cfg = load_config(config_dir=tmp_path)
    assert cfg.baud == DEFAULT_BAUD


# ── DRY_RUN env var truthy/falsy ──────────────────────────────────────────


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "True", "YES"])
def test_dry_run_truthy_values(value: str, tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_DRY_RUN, value)
    cfg = load_config(config_dir=tmp_path)
    assert cfg.dry_run is True


@pytest.mark.parametrize("value", ["0", "false", ""])
def test_dry_run_falsy_values(value: str, tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_DRY_RUN, value)
    cfg = load_config(config_dir=tmp_path)
    assert cfg.dry_run is False


def test_dry_run_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_DRY_RUN, raising=False)
    cfg = load_config(config_dir=tmp_path)
    assert cfg.dry_run is False
