# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for setup wizard firmware preparation helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from copilot_command_ring.boards import RUNTIME_ARDUINO, RUNTIME_CIRCUITPYTHON, RUNTIME_MICROPYTHON
from copilot_command_ring.firmware_install import (
    FirmwareInstallError,
    arduino_pin_expression,
    circuitpython_pin_expression,
    install_circuitpython_files,
    micropython_pin_expression,
    prepare_firmware_files,
)


def test_circuitpython_pin_expression_adds_board_prefix() -> None:
    assert circuitpython_pin_expression("D6") == "board.D6"
    assert circuitpython_pin_expression("board.GP6") == "board.GP6"
    assert circuitpython_pin_expression("gp6") == "board.GP6"
    assert circuitpython_pin_expression("auto") is None


def test_micropython_pin_expression_accepts_pin_wrapper() -> None:
    assert micropython_pin_expression("Pin(6)") == "6"
    assert micropython_pin_expression("18") == "18"
    assert micropython_pin_expression("GPIO6") == "6"
    assert micropython_pin_expression("auto") is None


def test_arduino_pin_expression_accepts_analog_and_numeric_pins() -> None:
    assert arduino_pin_expression("a0") == "A0"
    assert arduino_pin_expression("6") == "6"


def test_invalid_pin_expression_raises_clear_error() -> None:
    with pytest.raises(FirmwareInstallError, match="CircuitPython pins"):
        circuitpython_pin_expression("GPIO 6")


def test_prepare_circuitpython_patches_code_py(tmp_path: Path) -> None:
    prepared = prepare_firmware_files(RUNTIME_CIRCUITPYTHON, "board.A0", tmp_path)
    code_text = (tmp_path / "code.py").read_text(encoding="utf-8")
    assert prepared.runtime == RUNTIME_CIRCUITPYTHON
    assert "NEOPIXEL_PIN = board.A0" in code_text
    assert (tmp_path / "boot.py").is_file()


def test_prepare_micropython_patches_main_py(tmp_path: Path) -> None:
    prepare_firmware_files(RUNTIME_MICROPYTHON, "Pin(6)", tmp_path)
    main_text = (tmp_path / "main.py").read_text(encoding="utf-8")
    assert "NEOPIXEL_PIN = 6" in main_text
    assert (tmp_path / "ring_cdc.py").is_file()
    assert (tmp_path / "neopixel_compat.py").is_file()


def test_prepare_arduino_patches_header(tmp_path: Path) -> None:
    prepared = prepare_firmware_files(RUNTIME_ARDUINO, "A0", tmp_path)
    header_text = (prepared.directory / "copilot_types.h").read_text(encoding="utf-8")
    assert "#define NEOPIXEL_PIN      A0" in header_text
    assert (prepared.directory / "copilot_command_ring.ino").is_file()


def test_install_circuitpython_files_copies_prepared_files(tmp_path: Path) -> None:
    prepared_dir = tmp_path / "prepared"
    target = tmp_path / "CIRCUITPY"
    target.mkdir()
    prepared = prepare_firmware_files(RUNTIME_CIRCUITPYTHON, "board.D6", prepared_dir)

    written = install_circuitpython_files(prepared, target)

    assert target / "boot.py" in written
    assert target / "code.py" in written
    assert (target / "code.py").is_file()
