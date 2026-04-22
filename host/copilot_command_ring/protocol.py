# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Serial protocol — JSON Lines serialization."""

from __future__ import annotations

import json
from collections.abc import Mapping


def serialize_message(message: Mapping[str, object]) -> bytes:
    """Serialize an event dict to a newline-terminated UTF-8 JSON line."""
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


def deserialize_message(line: bytes) -> dict[str, object] | None:
    """Parse a raw serial line into a dict, or return None on failure."""
    try:
        result = json.loads(line.strip())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(result, dict):
        return None
    return result  # type: ignore[return-value]


def format_message_for_log(message: Mapping[str, object]) -> str:
    """Return a compact, deterministic string for debug logging."""
    return json.dumps(message, sort_keys=True)
