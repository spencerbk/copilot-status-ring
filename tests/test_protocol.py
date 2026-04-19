# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for copilot_command_ring.protocol (JSON Lines serialization)."""

from __future__ import annotations

import json

from copilot_command_ring.protocol import (
    deserialize_message,
    format_message_for_log,
    serialize_message,
)

# ── serialize_message ─────────────────────────────────────────────────────


def test_serialize_produces_utf8_bytes():
    result = serialize_message({"event": "sessionStart"})
    assert isinstance(result, bytes)
    result.decode("utf-8")  # should not raise


def test_serialize_ends_with_newline():
    result = serialize_message({"event": "sessionStart"})
    assert result.endswith(b"\n")


def test_serialize_body_is_valid_json():
    result = serialize_message({"event": "test", "state": "idle"})
    parsed = json.loads(result.strip())
    assert parsed == {"event": "test", "state": "idle"}


def test_serialize_uses_compact_format():
    result = serialize_message({"a": 1, "b": 2})
    text = result.decode("utf-8").strip()
    assert " " not in text  # no spaces around separators


# ── deserialize_message ───────────────────────────────────────────────────


def test_deserialize_roundtrips_with_serialize():
    original = {"event": "sessionStart", "state": "session_start"}
    wire = serialize_message(original)
    recovered = deserialize_message(wire)
    assert recovered == original


def test_deserialize_returns_none_for_malformed_json():
    assert deserialize_message(b"not json at all\n") is None


def test_deserialize_returns_none_for_json_array():
    assert deserialize_message(b'[1, 2, 3]\n') is None


def test_deserialize_returns_none_for_json_string():
    assert deserialize_message(b'"just a string"\n') is None


def test_deserialize_handles_empty_bytes():
    assert deserialize_message(b"") is None


def test_deserialize_handles_whitespace_only():
    assert deserialize_message(b"   \n") is None


# ── format_message_for_log ────────────────────────────────────────────────


def test_format_message_for_log_returns_sorted_keys():
    result = format_message_for_log({"z": 1, "a": 2, "m": 3})
    parsed = json.loads(result)
    assert list(parsed.keys()) == ["a", "m", "z"]


def test_format_message_for_log_returns_string():
    result = format_message_for_log({"event": "test"})
    assert isinstance(result, str)
