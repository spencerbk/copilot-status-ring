# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Health-check / diagnostic command for the Copilot Command Ring.

Backs the ``copilot-command-ring doctor`` CLI subcommand and the
``/status-ring-doctor`` slash command exposed by the Copilot CLI extension.

The doctor walks the same path a hook walks (config load -> port discovery
-> matcher -> lock -> serial write) and prints a human-friendly report so
a user can tell, in one command, *why* their ring isn't lighting up. Exit
code 0 means every hard check passed; exit code 1 means at least one did
not.

Output is intentionally plain ASCII so Windows consoles render cleanly
regardless of the active code page.

The command is deliberately a single end-to-end report rather than a
family of narrower commands (``/list-ports``, ``/test-pulse`` ...) -- a
single doctor command is easier to remember when you actually need it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .config import Config, ConfigMetadata, load_config_with_metadata
from .detect_ports import _match_port
from .events import normalize_event
from .sender import send_event
from .serial_lock import SerialLock, _lock_path, _read_lock_stamp

OK: str = "[ OK ]"
WARN: str = "[WARN]"
FAIL: str = "[FAIL]"
INFO: str = "[ -- ]"


@dataclass
class CheckResult:
    """A single doctor check outcome."""

    label: str
    status: str  # one of OK / WARN / FAIL / INFO
    message: str
    detail: list[str] | None = None

    @property
    def is_failure(self) -> bool:
        return self.status == FAIL


def _format_result(result: CheckResult) -> list[str]:
    lines = [f"{result.status} {result.label}: {result.message}"]
    if result.detail:
        lines.extend(f"        {line}" for line in result.detail)
    return lines


def _check_config(config: Config, meta: ConfigMetadata) -> CheckResult:
    if meta.parse_error is not None:
        return CheckResult(
            label="Config",
            status=WARN,
            message=f"failed to parse {meta.config_path}",
            detail=[meta.parse_error, "using built-in defaults + env overrides"],
        )

    if meta.config_path is None:
        location = "no .copilot-command-ring.local.json found (using defaults)"
    else:
        location = f"loaded from {meta.config_path}"

    detail = [
        f"serial_port    = {config.serial_port!r}",
        f"baud           = {config.baud}",
        f"pixel_count    = {config.pixel_count}",
        f"brightness     = {config.brightness:.3f}",
        f"idle_mode      = {config.idle_mode}",
        f"lock_timeout   = {config.lock_timeout:.2f}s",
        f"device_match   = {config.device_match_descriptions}",
    ]
    return CheckResult(
        label="Config",
        status=OK,
        message=location,
        detail=detail,
    )


def _check_dry_run(config: Config) -> CheckResult:
    if config.dry_run:
        return CheckResult(
            label="Dry-run",
            status=FAIL,
            message="dry_run is enabled -- hooks will NOT write to the ring",
            detail=[
                "unset COPILOT_RING_DRY_RUN, or remove dry_run from "
                ".copilot-command-ring.local.json",
            ],
        )
    return CheckResult(
        label="Dry-run",
        status=OK,
        message="disabled (hooks will write to hardware)",
    )


def _check_pyserial() -> CheckResult:
    try:
        import serial  # noqa: F401, PLC0415
    except ImportError:
        return CheckResult(
            label="pyserial",
            status=FAIL,
            message="not installed",
            detail=[
                "install with: pip install pyserial",
                "or reinstall the package: pip install copilot-command-ring",
            ],
        )
    return CheckResult(label="pyserial", status=OK, message="available")


def _enumerate_ports() -> tuple[CheckResult, list[object]]:
    try:
        from serial.tools.list_ports import comports  # noqa: PLC0415
    except ImportError:
        return (
            CheckResult(
                label="Ports",
                status=FAIL,
                message="cannot enumerate (pyserial.tools.list_ports unavailable)",
            ),
            [],
        )

    try:
        ports = list(comports())
    except Exception as exc:  # noqa: BLE001
        return (
            CheckResult(
                label="Ports",
                status=FAIL,
                message=f"enumeration raised: {exc}",
            ),
            [],
        )

    if not ports:
        return (
            CheckResult(
                label="Ports",
                status=WARN,
                message="no serial ports detected by Windows/macOS/Linux",
                detail=[
                    "is the USB cable a data cable (not charge-only)?",
                    "is the device powered on and enumerated?",
                    "try a different USB port",
                ],
            ),
            [],
        )

    detail = [
        f"{getattr(p, 'device', '?')}  |  "
        f"{getattr(p, 'description', '?')}  |  "
        f"{getattr(p, 'hwid', '?')}"
        for p in ports
    ]
    return (
        CheckResult(
            label="Ports",
            status=OK,
            message=f"{len(ports)} port(s) discovered",
            detail=detail,
        ),
        ports,
    )


def _check_match(config: Config, ports: list[object]) -> CheckResult:
    if config.serial_port:
        # Explicit port: verify it is actually enumerated. detect_serial_port
        # returns the configured value as-is without checking — without this
        # check, --no-ping on a stale config would false-clear.
        for port in ports:
            if getattr(port, "device", None) == config.serial_port:
                return CheckResult(
                    label="Match",
                    status=OK,
                    message=(
                        f"explicit serial_port {config.serial_port!r} "
                        "is present in enumeration"
                    ),
                )
        return CheckResult(
            label="Match",
            status=FAIL,
            message=(
                f"explicit serial_port {config.serial_port!r} "
                "is NOT in enumeration"
            ),
            detail=[
                "the configured port is not currently visible to the OS",
                "check the cable, replug the device, or update serial_port",
            ],
        )

    if not ports:
        return CheckResult(
            label="Match",
            status=FAIL,
            message="no ports to match against",
        )

    matches = []
    for port in ports:
        matched = _match_port(
            getattr(port, "description", "") or "",
            config.device_match_descriptions,
        )
        if matched is not None:
            matches.append((getattr(port, "device", "?"), matched))

    if matches:
        detail = [f"{device}  matched on  {pattern!r}" for device, pattern in matches]
        return CheckResult(
            label="Match",
            status=OK,
            message=f"{len(matches)} port(s) matched device descriptors",
            detail=detail,
        )

    return CheckResult(
        label="Match",
        status=FAIL,
        message="no enumerated port matched device_match_descriptions",
        detail=[
            f"tried: {config.device_match_descriptions}",
            "if your device IS in the Ports list above, add a substring of",
            "its description to device_match.description_contains in",
            ".copilot-command-ring.local.json, or set serial_port directly.",
        ],
    )


def _check_lock(config: Config) -> CheckResult:
    lock = SerialLock(timeout=0.1)
    with lock as acquired:
        if acquired:
            return CheckResult(
                label="Lock",
                status=OK,
                message=f"free ({_lock_path()})",
            )

    # Could not acquire — observe why.
    stamp = _read_lock_stamp(_lock_path())
    if stamp is not None:
        pid, mtime = stamp
        import time  # noqa: PLC0415

        age = max(0.0, time.time() - mtime)
        return CheckResult(
            label="Lock",
            status=WARN,
            message=f"held by pid={pid} (age {age:.1f}s)",
            detail=[
                "another Copilot CLI session is probably writing right now",
                f"timeout={config.lock_timeout:.2f}s -- rerun if persistent",
            ],
        )
    return CheckResult(
        label="Lock",
        status=WARN,
        message="could not acquire 0.1s probe (no stamp readable)",
    )


def _check_ping(config: Config) -> CheckResult:
    # Use a `notification` event because it maps to STATE_NOTIFY which is
    # transient (no entry in STATE_TTL_DEFAULTS) — sending session_start
    # would leave the ring in a fake "active" state for up to 60 seconds.
    message = normalize_event(
        "notification",
        {"notification_type": "doctor_ping", "message": "doctor ping"},
    )
    sent = send_event(config, message)
    if sent:
        return CheckResult(
            label="Ping",
            status=OK,
            message="sent transient notification -- ring should briefly flash",
        )
    return CheckResult(
        label="Ping",
        status=FAIL,
        message="send_event returned False (see DEBUG log for details)",
        detail=[
            "rerun with COPILOT_RING_LOG_LEVEL=DEBUG for the full failure path",
        ],
    )


def run_doctor(
    *,
    config_dir: Path | None = None,
    ping: bool = True,
    stream: TextIO | None = None,
) -> int:
    """Run all doctor checks and write a human-readable report.

    Returns ``0`` if every hard check passed, ``1`` otherwise.
    """
    out: TextIO = stream if stream is not None else sys.stdout

    config, meta = load_config_with_metadata(config_dir)
    results: list[CheckResult] = [_check_config(config, meta)]

    dry = _check_dry_run(config)
    results.append(dry)

    pyserial_result = _check_pyserial()
    results.append(pyserial_result)

    if pyserial_result.is_failure:
        ports: list[object] = []
        ports_result = CheckResult(
            label="Ports",
            status=INFO,
            message="skipped (pyserial unavailable)",
        )
        match_result = CheckResult(
            label="Match",
            status=INFO,
            message="skipped (pyserial unavailable)",
        )
        lock_result = CheckResult(
            label="Lock",
            status=INFO,
            message="skipped (pyserial unavailable)",
        )
    else:
        ports_result, ports = _enumerate_ports()
        match_result = _check_match(config, ports)
        lock_result = _check_lock(config)

    results.extend([ports_result, match_result, lock_result])

    if not ping:
        results.append(
            CheckResult(
                label="Ping",
                status=INFO,
                message="skipped (--no-ping)",
            ),
        )
    elif dry.is_failure or pyserial_result.is_failure or match_result.is_failure:
        # Don't attempt a ping when an upstream check guarantees failure —
        # the resulting noise distracts from the real diagnosis.
        results.append(
            CheckResult(
                label="Ping",
                status=INFO,
                message="skipped (upstream check failed)",
            ),
        )
    else:
        results.append(_check_ping(config))

    out.write("Copilot Command Ring -- doctor report\n")
    out.write("-" * 38 + "\n")
    for result in results:
        for line in _format_result(result):
            out.write(line + "\n")
    out.write("-" * 38 + "\n")

    failed = [r for r in results if r.is_failure]
    if failed:
        out.write(
            f"RESULT: FAIL -- {len(failed)} check(s) failed: "
            + ", ".join(r.label for r in failed)
            + "\n",
        )
        return 1

    warned = [r for r in results if r.status == WARN]
    if warned:
        out.write(
            f"RESULT: OK with warnings ({len(warned)} warning(s): "
            + ", ".join(r.label for r in warned)
            + ")\n",
        )
    else:
        out.write("RESULT: OK -- all checks passed\n")
    return 0
