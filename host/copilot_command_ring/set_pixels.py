# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""One-shot helper to change the ring's LED (pixel) count.

Backs the ``copilot-command-ring set-pixels <count>`` subcommand. Updates
only the ``pixel_count`` field of the local JSON config, preserving every
other field. The host sends ``pixel_count`` to the firmware on each hook
event, and the firmware applies it at runtime, so no reflash is needed —
the ring picks up the new count on the next Copilot CLI event.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import find_config_path
from .constants import CONFIG_FILE_NAME, MAX_PIXEL_COUNT
from .logging_util import get_logger


def _user_home() -> Path:
    """Indirection over ``Path.home()`` so tests can isolate the global path."""
    return Path.home()


def _target_config_path(start: Path) -> Path:
    """Resolve which config file ``set-pixels`` should write.

    Prefers the config file the host would actually load (so the change
    takes effect): the first match walking *start* and its parents, then
    the wizard's global ``~/<CONFIG_FILE_NAME>``. When no file exists
    anywhere, returns the global path so a fresh config is created there.
    """
    existing = find_config_path(start)
    if existing is not None:
        return existing
    return _user_home() / CONFIG_FILE_NAME


def run_set_pixels(count: int, *, config_dir: Path | None = None) -> bool:
    """Set ``pixel_count`` to *count* in the local config file.

    Returns ``True`` on success, ``False`` on invalid input or write
    failure. Existing config fields are preserved; only ``pixel_count``
    is overwritten.
    """
    log = get_logger()

    if isinstance(count, bool) or count <= 0:
        print(f"Error: pixel count must be a positive integer, got {count!r}")
        return False
    if count > MAX_PIXEL_COUNT:
        print(f"Error: pixel count must be <= {MAX_PIXEL_COUNT}, got {count}")
        return False

    start = Path(config_dir) if config_dir is not None else Path.cwd()
    target = _target_config_path(start)

    existing: dict[str, object] = {}
    if target.is_file():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.debug("Ignoring unparseable config %s: %s", target, exc)
            data = None
        if isinstance(data, dict):
            existing = data

    existing["pixel_count"] = count

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Error: could not write {target}: {exc}")
        return False

    print(f"Set pixel_count = {count} in {target}")
    print("The ring will use the new count on the next Copilot CLI event.")
    return True
