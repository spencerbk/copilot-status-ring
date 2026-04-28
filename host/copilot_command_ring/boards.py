# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Supported board, firmware runtime, and NeoPixel pin metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

RUNTIME_CIRCUITPYTHON: Final[str] = "circuitpython"
RUNTIME_MICROPYTHON: Final[str] = "micropython"
RUNTIME_ARDUINO: Final[str] = "arduino"

RUNTIME_LABELS: Final[dict[str, str]] = {
    RUNTIME_CIRCUITPYTHON: "CircuitPython",
    RUNTIME_MICROPYTHON: "MicroPython",
    RUNTIME_ARDUINO: "Arduino",
}

FIRMWARE_COPY: Final[str] = "copy"
FIRMWARE_MPREMOTE: Final[str] = "mpremote"
FIRMWARE_MANUAL: Final[str] = "manual"


@dataclass(frozen=True)
class RuntimeOption:
    """Firmware support metadata for one board/runtime combination."""

    runtime: str
    default_pin: str | None
    firmware_install: str
    pin_auto_detect: bool = False
    requires_manual_pin: bool = False
    notes: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        """Human-readable runtime name."""
        return RUNTIME_LABELS[self.runtime]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation for CLI/extensions."""
        return {
            "runtime": self.runtime,
            "label": self.label,
            "default_pin": self.default_pin,
            "firmware_install": self.firmware_install,
            "pin_auto_detect": self.pin_auto_detect,
            "requires_manual_pin": self.requires_manual_pin,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class BoardOption:
    """Supported setup-wizard board metadata."""

    id: str
    name: str
    runtimes: tuple[RuntimeOption, ...]
    aliases: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def runtime(self, runtime_id: str) -> RuntimeOption:
        """Return metadata for *runtime_id* or raise ``KeyError``."""
        for option in self.runtimes:
            if option.runtime == runtime_id:
                return option
        raise KeyError(f"{self.name} does not support {runtime_id}")

    def supports_runtime(self, runtime_id: str) -> bool:
        """Return whether this board supports *runtime_id*."""
        return any(option.runtime == runtime_id for option in self.runtimes)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation for CLI/extensions."""
        return {
            "id": self.id,
            "name": self.name,
            "aliases": list(self.aliases),
            "notes": list(self.notes),
            "runtimes": [runtime.to_dict() for runtime in self.runtimes],
        }


def _circuitpython(pin: str) -> RuntimeOption:
    return RuntimeOption(
        runtime=RUNTIME_CIRCUITPYTHON,
        default_pin=pin,
        firmware_install=FIRMWARE_COPY,
        pin_auto_detect=True,
        notes=("Recommended default; firmware can auto-detect this board family.",),
    )


def _micropython_autopin(pin: str = "Pin(6)") -> RuntimeOption:
    return RuntimeOption(
        runtime=RUNTIME_MICROPYTHON,
        default_pin=pin,
        firmware_install=FIRMWARE_MPREMOTE,
        pin_auto_detect=True,
        notes=("MicroPython auto-detects RP2040/RP2350-family GPIO 6 boards.",),
    )


def _micropython_manual(*notes: str) -> RuntimeOption:
    return RuntimeOption(
        runtime=RUNTIME_MICROPYTHON,
        default_pin=None,
        firmware_install=FIRMWARE_MPREMOTE,
        requires_manual_pin=True,
        notes=notes or ("Set NEOPIXEL_PIN to the GPIO number for the pin you wired.",),
    )


def _arduino(pin: str, *notes: str) -> RuntimeOption:
    return RuntimeOption(
        runtime=RUNTIME_ARDUINO,
        default_pin=pin,
        firmware_install=FIRMWARE_MANUAL,
        requires_manual_pin=False,
        notes=notes or ("Upload with Arduino IDE or arduino-cli after installing libraries.",),
    )


SUPPORTED_BOARDS: Final[tuple[BoardOption, ...]] = (
    BoardOption(
        id="raspberry-pi-pico",
        name="Raspberry Pi Pico / Pico W",
        aliases=("pico", "pico-w", "rp2040"),
        runtimes=(
            _circuitpython("board.GP6"),
            _micropython_autopin(),
            _arduino("6"),
        ),
    ),
    BoardOption(
        id="adafruit-feather-rp2040",
        name="Adafruit Feather RP2040",
        aliases=("feather-rp2040",),
        runtimes=(
            _circuitpython("board.D6"),
            _micropython_autopin(),
            _arduino("6"),
        ),
    ),
    BoardOption(
        id="adafruit-qt-py-rp2040",
        name="Adafruit QT Py RP2040",
        aliases=("qt-py-rp2040", "qtpy-rp2040"),
        runtimes=(
            _circuitpython("board.A0"),
            _micropython_manual(
                "MicroPython requires a manual GPIO-number override for QT Py boards.",
            ),
            _arduino("A0"),
        ),
    ),
    BoardOption(
        id="adafruit-feather-esp32-s2",
        name="Adafruit Feather ESP32-S2",
        aliases=("feather-esp32-s2",),
        runtimes=(
            _circuitpython("board.D6"),
            _micropython_manual(
                "MicroPython requires a manual GPIO-number override on ESP32-S2.",
            ),
            _arduino("6"),
        ),
    ),
    BoardOption(
        id="adafruit-feather-esp32-s3",
        name="Adafruit Feather ESP32-S3",
        aliases=("feather-esp32-s3",),
        runtimes=(
            _circuitpython("board.D6"),
            _micropython_manual(
                "MicroPython requires a manual GPIO-number override on ESP32-S3.",
            ),
            _arduino("6"),
        ),
    ),
    BoardOption(
        id="adafruit-qt-py-esp32-s2",
        name="Adafruit QT Py ESP32-S2",
        aliases=("qt-py-esp32-s2", "qtpy-esp32-s2"),
        runtimes=(
            _circuitpython("board.A0"),
            _micropython_manual(
                "MicroPython requires a manual GPIO-number override for QT Py boards.",
            ),
            _arduino("A0"),
        ),
    ),
    BoardOption(
        id="adafruit-qt-py-esp32-s3",
        name="Adafruit QT Py ESP32-S3",
        aliases=("qt-py-esp32-s3", "qtpy-esp32-s3"),
        runtimes=(
            _circuitpython("board.A0"),
            _micropython_manual(
                "MicroPython requires a manual GPIO-number override for QT Py boards.",
            ),
            _arduino("A0"),
        ),
    ),
    BoardOption(
        id="seeed-xiao-rp2350",
        name="Seeed Studio XIAO RP2350",
        aliases=("xiao-rp2350",),
        runtimes=(
            _circuitpython("board.D6"),
            _micropython_autopin(),
        ),
        notes=("Arduino support is not available in the current project docs.",),
    ),
    BoardOption(
        id="seeed-xiao-esp32-c6",
        name="Seeed Studio XIAO ESP32-C6",
        aliases=("xiao-esp32-c6",),
        runtimes=(
            _circuitpython("board.D6"),
            _micropython_manual(
                "MicroPython runs in degraded mode on ESP32-C6.",
                "Set NEOPIXEL_PIN to the GPIO number for the pin you wired.",
            ),
            _arduino("6"),
        ),
    ),
)

_BOARD_BY_ID: Final[dict[str, BoardOption]] = {board.id: board for board in SUPPORTED_BOARDS}
_ALIAS_TO_ID: Final[dict[str, str]] = {
    alias: board.id for board in SUPPORTED_BOARDS for alias in board.aliases
}


def list_boards() -> tuple[BoardOption, ...]:
    """Return all boards supported by the setup wizard."""
    return SUPPORTED_BOARDS


def get_board(board_id_or_alias: str) -> BoardOption:
    """Return a board by canonical id or alias."""
    normalized = board_id_or_alias.strip().lower()
    board_id = _ALIAS_TO_ID.get(normalized, normalized)
    try:
        return _BOARD_BY_ID[board_id]
    except KeyError as exc:
        raise KeyError(f"Unsupported board: {board_id_or_alias}") from exc


def get_runtime(board_id_or_alias: str, runtime_id: str) -> RuntimeOption:
    """Return runtime metadata for a board/runtime pair."""
    board = get_board(board_id_or_alias)
    try:
        return board.runtime(runtime_id)
    except KeyError as exc:
        raise KeyError(f"{board.name} does not support {runtime_id}") from exc


def default_runtime(board_id_or_alias: str) -> RuntimeOption:
    """Return the recommended runtime for a board."""
    board = get_board(board_id_or_alias)
    if board.supports_runtime(RUNTIME_CIRCUITPYTHON):
        return board.runtime(RUNTIME_CIRCUITPYTHON)
    return board.runtimes[0]


def default_pin(board_id_or_alias: str, runtime_id: str) -> str | None:
    """Return the documented default pin for a board/runtime pair."""
    return get_runtime(board_id_or_alias, runtime_id).default_pin


def options_payload() -> dict[str, object]:
    """Return setup options in the JSON shape consumed by the extension."""
    return {
        "default_runtime": RUNTIME_CIRCUITPYTHON,
        "runtimes": dict(RUNTIME_LABELS),
        "boards": [board.to_dict() for board in SUPPORTED_BOARDS],
    }
