# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Configuration loading for the Copilot Command Ring host bridge."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .constants import (
    CONFIG_FILE_NAME,
    DEFAULT_BAUD,
    DEFAULT_BRIGHTNESS,
    DEFAULT_DESCRIPTION_CONTAINS,
    DEFAULT_IDLE_MODE,
    DEFAULT_LOCK_TIMEOUT,
    DEFAULT_PIXEL_COUNT,
    ENV_BAUD,
    ENV_BRIGHTNESS,
    ENV_DRY_RUN,
    ENV_PORT,
)
from .logging_util import get_logger


@dataclass
class Config:
    """Runtime configuration for the host bridge."""

    serial_port: str | None = None
    baud: int = DEFAULT_BAUD
    pixel_count: int = DEFAULT_PIXEL_COUNT
    brightness: float = DEFAULT_BRIGHTNESS
    idle_mode: str = DEFAULT_IDLE_MODE
    dry_run: bool = False
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT
    device_match_descriptions: list[str] = field(
        default_factory=lambda: list(DEFAULT_DESCRIPTION_CONTAINS),
    )


def _find_config_file(start: Path) -> Path | None:
    """Search *start* and its parents for the config file.

    Returns the first match or ``None``.
    """
    current = start.resolve()
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_FILE_NAME
        if candidate.is_file():
            return candidate
    return None


def _apply_file(cfg: Config, path: Path) -> None:
    """Overlay values from a JSON config file onto *cfg*."""
    log = get_logger()
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        log.debug("Ignoring config file %s: %s", path, exc)
        return

    if not isinstance(data, dict):
        log.debug("Config file %s is not a JSON object; ignoring", path)
        return

    log.debug("Loaded config from %s", path)

    if "serial_port" in data and isinstance(data["serial_port"], str):
        cfg.serial_port = data["serial_port"]
    if "baud" in data and isinstance(data["baud"], int):
        cfg.baud = data["baud"]
    if "pixel_count" in data and isinstance(data["pixel_count"], int):
        cfg.pixel_count = data["pixel_count"]
    if "brightness" in data and isinstance(data["brightness"], (int, float)):
        cfg.brightness = float(data["brightness"])
    if "idle_mode" in data and isinstance(data["idle_mode"], str):
        cfg.idle_mode = data["idle_mode"]

    device_match = data.get("device_match")
    if isinstance(device_match, dict):
        desc = device_match.get("description_contains")
        if isinstance(desc, list) and all(isinstance(s, str) for s in desc):
            cfg.device_match_descriptions = list(desc)


def _apply_env(cfg: Config) -> None:
    """Overlay environment-variable overrides onto *cfg*."""
    log = get_logger()

    port = os.environ.get(ENV_PORT)
    if port:
        log.debug("ENV override %s=%s", ENV_PORT, port)
        cfg.serial_port = port

    baud_str = os.environ.get(ENV_BAUD)
    if baud_str:
        try:
            cfg.baud = int(baud_str)
            log.debug("ENV override %s=%d", ENV_BAUD, cfg.baud)
        except ValueError:
            log.debug("Invalid %s value %r; ignoring", ENV_BAUD, baud_str)

    brightness_str = os.environ.get(ENV_BRIGHTNESS)
    if brightness_str:
        try:
            cfg.brightness = float(brightness_str)
            log.debug("ENV override %s=%s", ENV_BRIGHTNESS, cfg.brightness)
        except ValueError:
            log.debug(
                "Invalid %s value %r; ignoring", ENV_BRIGHTNESS, brightness_str,
            )

    dry_run_str = os.environ.get(ENV_DRY_RUN, "")
    if dry_run_str.strip().lower() in ("1", "true", "yes"):
        cfg.dry_run = True
        log.debug("ENV override %s=%s (dry_run=True)", ENV_DRY_RUN, dry_run_str)


def load_config(config_dir: Path | None = None) -> Config:
    """Build a :class:`Config` by merging defaults, file, and env vars.

    Override precedence (highest wins):
        environment variable > local config file > built-in default

    Parameters
    ----------
    config_dir:
        Directory to start searching for the config file.
        Defaults to the current working directory.
    """
    log = get_logger()
    cfg = Config()

    start = Path(config_dir) if config_dir is not None else Path.cwd()
    config_path = _find_config_file(start)
    if config_path is not None:
        _apply_file(cfg, config_path)
    else:
        log.debug("No config file (%s) found", CONFIG_FILE_NAME)

    _apply_env(cfg)

    log.debug(
        "Final config: port=%s baud=%d pixels=%d brightness=%.2f "
        "idle=%s dry_run=%s",
        cfg.serial_port,
        cfg.baud,
        cfg.pixel_count,
        cfg.brightness,
        cfg.idle_mode,
        cfg.dry_run,
    )
    return cfg
