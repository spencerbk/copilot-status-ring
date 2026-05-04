# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for setup wizard board metadata."""

from __future__ import annotations

import pytest
from copilot_command_ring.boards import (
    RUNTIME_ARDUINO,
    RUNTIME_CIRCUITPYTHON,
    RUNTIME_MICROPYTHON,
    default_pin,
    default_runtime,
    get_board,
    get_runtime,
    list_boards,
    options_payload,
)


def test_board_matrix_includes_documented_boards() -> None:
    names = {board.name for board in list_boards()}
    assert names == {
        "Raspberry Pi Pico / Pico W",
        "Adafruit Feather RP2040",
        "Adafruit QT Py RP2040",
        "Adafruit Feather ESP32-S2",
        "Adafruit Feather ESP32-S3",
        "Adafruit QT Py ESP32-S2",
        "Adafruit QT Py ESP32-S3",
        "Seeed Studio XIAO RP2350",
        "Seeed Studio XIAO ESP32-C6",
    }


@pytest.mark.parametrize(
    ("board_id", "pin"),
    [
        ("raspberry-pi-pico", "board.GP6"),
        ("adafruit-feather-rp2040", "board.D6"),
        ("adafruit-qt-py-rp2040", "board.A0"),
        ("adafruit-feather-esp32-s2", "board.D6"),
        ("adafruit-feather-esp32-s3", "board.D6"),
        ("adafruit-qt-py-esp32-s2", "board.A0"),
        ("adafruit-qt-py-esp32-s3", "board.A0"),
        ("seeed-xiao-rp2350", "board.D6"),
        ("seeed-xiao-esp32-c6", "board.D6"),
    ],
)
def test_circuitpython_default_pins_match_hardware_docs(board_id: str, pin: str) -> None:
    assert default_pin(board_id, RUNTIME_CIRCUITPYTHON) == pin


def test_default_runtime_is_circuitpython() -> None:
    assert default_runtime("raspberry-pi-pico").runtime == RUNTIME_CIRCUITPYTHON


def test_xiao_rp2350_does_not_offer_arduino() -> None:
    board = get_board("seeed-xiao-rp2350")
    assert not board.supports_runtime(RUNTIME_ARDUINO)


def test_qt_py_micropython_requires_manual_pin() -> None:
    runtime = get_runtime("adafruit-qt-py-rp2040", RUNTIME_MICROPYTHON)
    assert runtime.default_pin is None
    assert runtime.requires_manual_pin is True


def test_options_payload_is_json_ready() -> None:
    payload = options_payload()
    assert payload["default_runtime"] == RUNTIME_CIRCUITPYTHON
    boards = payload["boards"]
    assert isinstance(boards, list)
    assert boards[0]["id"] == "raspberry-pi-pico"
