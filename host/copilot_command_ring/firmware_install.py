# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Firmware preparation and safe install helpers for the setup wizard."""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import string
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .boards import RUNTIME_ARDUINO, RUNTIME_CIRCUITPYTHON, RUNTIME_MICROPYTHON

CommandRunner = Callable[[Sequence[str]], None]


class FirmwareInstallError(RuntimeError):
    """Raised when firmware preparation or installation cannot proceed."""


@dataclass(frozen=True)
class PreparedFirmware:
    """Files prepared for one firmware runtime."""

    runtime: str
    directory: Path
    files: tuple[Path, ...]
    manual_steps: tuple[str, ...] = ()


def repo_root() -> Path:
    """Return the repository root for bundled firmware files."""
    return Path(__file__).resolve().parents[2]


def _replace_assignment(text: str, name: str, value: str) -> str:
    pattern = re.compile(rf"^({re.escape(name)}\s*=\s*).*$", re.MULTILINE)
    replacement = rf"\g<1>{value}"
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise FirmwareInstallError(f"Could not find {name} assignment")
    return updated


def _replace_define(text: str, name: str, value: str) -> str:
    pattern = re.compile(rf"^(#define\s+{re.escape(name)}\s+).*$", re.MULTILINE)
    replacement = rf"\g<1>{value}"
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise FirmwareInstallError(f"Could not find {name} define")
    return updated


def circuitpython_pin_expression(pin: str | None) -> str | None:
    """Normalize a CircuitPython pin string to a ``board`` expression."""
    if pin is None or not pin.strip():
        return None
    value = pin.strip()
    if value.lower() in {"auto", "none"}:
        return None
    if value.lower().startswith("board."):
        suffix = value.split(".", 1)[1].upper()
        if re.fullmatch(r"[A-Z]+[0-9]*", suffix):
            return f"board.{suffix}"
    if re.fullmatch(r"[A-Za-z]+[0-9]*", value):
        return f"board.{value.upper()}"
    raise FirmwareInstallError(
        "CircuitPython pins must look like board.D6, board.GP6, or board.A0"
    )


def micropython_pin_expression(pin: str | None) -> str | None:
    """Normalize a MicroPython pin string to a GPIO integer expression."""
    if pin is None or not pin.strip():
        return None
    value = pin.strip()
    if value.lower() in {"auto", "none"}:
        return None
    match = re.fullmatch(r"Pin\((\d+)\)", value)
    if match:
        return match.group(1)
    match = re.fullmatch(r"GPIO\s*(\d+)", value, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    if re.fullmatch(r"\d+", value):
        return value
    raise FirmwareInstallError("MicroPython pins must be GPIO numbers, such as 6 or Pin(6)")


def arduino_pin_expression(pin: str | None) -> str | None:
    """Normalize an Arduino pin string for ``#define NEOPIXEL_PIN``."""
    if pin is None or not pin.strip():
        return None
    value = pin.strip()
    if value.lower() in {"auto", "none"}:
        return None
    normalized = value.upper()
    if re.fullmatch(r"(A\d+|\d+)", normalized):
        return normalized
    raise FirmwareInstallError("Arduino pins must look like 6 or A0")


def _copy_text_file(source: Path, destination: Path, text: str | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        shutil.copy2(source, destination)
    else:
        destination.write_text(text, encoding="utf-8")
    return destination


def prepare_firmware_files(
    runtime: str,
    data_pin: str | None,
    output_dir: Path,
    *,
    source_root: Path | None = None,
) -> PreparedFirmware:
    """Copy firmware into *output_dir*, patching the data pin when requested."""
    root = source_root or repo_root()
    output = output_dir.resolve()

    if runtime == RUNTIME_CIRCUITPYTHON:
        source_dir = root / "firmware" / "circuitpython"
        pin_expr = circuitpython_pin_expression(data_pin)
        code_text = (source_dir / "code.py").read_text(encoding="utf-8")
        if pin_expr is not None:
            code_text = _replace_assignment(code_text, "NEOPIXEL_PIN", pin_expr)
        files = (
            _copy_text_file(source_dir / "boot.py", output / "boot.py"),
            _copy_text_file(source_dir / "code.py", output / "code.py", code_text),
        )
        return PreparedFirmware(
            runtime=runtime,
            directory=output,
            files=files,
            manual_steps=(
                "Copy neopixel.mpy from the Adafruit CircuitPython Bundle to CIRCUITPY/lib/.",
            ),
        )

    if runtime == RUNTIME_MICROPYTHON:
        source_dir = root / "firmware" / "micropython"
        pin_expr = micropython_pin_expression(data_pin)
        main_text = (source_dir / "main.py").read_text(encoding="utf-8")
        if pin_expr is not None:
            main_text = _replace_assignment(main_text, "NEOPIXEL_PIN", pin_expr)
        files = (
            _copy_text_file(source_dir / "boot.py", output / "boot.py"),
            _copy_text_file(source_dir / "ring_cdc.py", output / "ring_cdc.py"),
            _copy_text_file(source_dir / "main.py", output / "main.py", main_text),
            _copy_text_file(
                source_dir / "neopixel_compat.py",
                output / "neopixel_compat.py",
            ),
        )
        return PreparedFirmware(runtime=runtime, directory=output, files=files)

    if runtime == RUNTIME_ARDUINO:
        source_dir = root / "firmware" / "arduino" / "copilot_command_ring"
        target_dir = output / "copilot_command_ring"
        pin_expr = arduino_pin_expression(data_pin)
        header_text = (source_dir / "copilot_types.h").read_text(encoding="utf-8")
        if pin_expr is not None:
            header_text = _replace_define(header_text, "NEOPIXEL_PIN", pin_expr)

        files = []
        for path in source_dir.iterdir():
            destination = target_dir / path.name
            if path.name == "copilot_types.h":
                files.append(_copy_text_file(path, destination, header_text))
            elif path.is_file():
                files.append(_copy_text_file(path, destination))
        return PreparedFirmware(
            runtime=runtime,
            directory=target_dir,
            files=tuple(files),
            manual_steps=(
                "Install the Adafruit NeoPixel Arduino library.",
                f"Open and upload {target_dir / 'copilot_command_ring.ino'}.",
            ),
        )

    raise FirmwareInstallError(f"Unsupported firmware runtime: {runtime}")


def _windows_volume_label(root: Path) -> str:
    label_buffer = ctypes.create_unicode_buffer(261)
    result = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
        ctypes.c_wchar_p(str(root)),
        label_buffer,
        len(label_buffer),
        None,
        None,
        None,
        None,
        0,
    )
    if result:
        return label_buffer.value
    return ""


def find_circuitpython_drive() -> Path | None:
    """Return a mounted ``CIRCUITPY`` drive path when one is visible."""
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:\\")
            if root.exists() and _windows_volume_label(root).upper() == "CIRCUITPY":
                return root
        return None

    candidates = [Path("/Volumes/CIRCUITPY")]
    user = os.environ.get("USER")
    if user:
        candidates.extend(
            [
                Path("/media") / user / "CIRCUITPY",
                Path("/run/media") / user / "CIRCUITPY",
            ]
        )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def install_circuitpython_files(prepared: PreparedFirmware, target_drive: Path) -> tuple[Path, ...]:
    """Copy prepared CircuitPython files to a mounted ``CIRCUITPY`` drive."""
    if prepared.runtime != RUNTIME_CIRCUITPYTHON:
        raise FirmwareInstallError("Prepared firmware is not CircuitPython")
    if not target_drive.is_dir():
        raise FirmwareInstallError(f"CircuitPython target is not a directory: {target_drive}")

    written = []
    for file_path in prepared.files:
        target = target_drive / file_path.name
        shutil.copy2(file_path, target)
        written.append(target)
    return tuple(written)


def install_circuitpython_neopixel(
    target_drive: Path,
    python_executable: Path,
    *,
    runner: CommandRunner,
) -> None:
    """Install the CircuitPython ``neopixel`` library with ``circup``."""
    if not target_drive.is_dir():
        raise FirmwareInstallError(f"CircuitPython target is not a directory: {target_drive}")

    (target_drive / "lib").mkdir(exist_ok=True)
    try:
        runner([str(python_executable), "-m", "pip", "install", "--upgrade", "circup"])
        runner(
            [
                str(python_executable),
                "-m",
                "circup",
                "--path",
                str(target_drive),
                "install",
                "neopixel",
            ]
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise FirmwareInstallError(
            "Could not install neopixel automatically; copy neopixel.mpy from the "
            "Adafruit CircuitPython Bundle to CIRCUITPY/lib/."
        ) from exc


def install_micropython_files(
    prepared: PreparedFirmware,
    python_executable: Path,
    *,
    runner: CommandRunner,
) -> None:
    """Install MicroPython dependencies and copy prepared files with ``mpremote``."""
    if prepared.runtime != RUNTIME_MICROPYTHON:
        raise FirmwareInstallError("Prepared firmware is not MicroPython")

    runner([str(python_executable), "-m", "pip", "install", "--upgrade", "mpremote"])
    runner([str(python_executable), "-m", "mpremote", "mip", "install", "usb-device-cdc"])
    for file_path in prepared.files:
        runner(
            [
                str(python_executable),
                "-m",
                "mpremote",
                "cp",
                str(file_path),
                f":{file_path.name}",
            ]
        )
    runner([str(python_executable), "-m", "mpremote", "reset"])


def run_checked(command: Sequence[str]) -> None:
    """Run a command and raise a concise firmware error on failure."""
    try:
        subprocess.run(list(command), check=True)
    except subprocess.CalledProcessError as exc:
        raise FirmwareInstallError(f"Command failed with exit {exc.returncode}: {command}") from exc
