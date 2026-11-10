# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Ownership-safe deployment for the GitHub Copilot App user extension."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
import re
import secrets
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

MARKER_NAME = ".copilot-command-ring-managed.json"
EXTENSION_NAME = "copilot-app-status-ring"
OWNER = "copilot-command-ring"
SCHEMA_VERSION = 1
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MARKER_KEYS = {
    "schema_version",
    "owner",
    "extension",
    "active_bridge_sha256",
    "tracked_releases",
    "mode",
}
_TOKEN_PATTERN = r"[0-9a-f]{32}"
_STAGE_PREFIX = f".{EXTENSION_NAME}.stage-"
_RELEASE_STAGE_PREFIX = ".copilot-command-ring-release-"
_RELEASE_BACKUP_PREFIX = ".copilot-command-ring-release-backup-"
_INITIAL_ROLLBACK_PREFIX = ".copilot-command-ring-initial-rollback-"
_STAGE_TEMP_PATTERN = re.compile(
    rf"^{re.escape(_STAGE_PREFIX)}{_TOKEN_PATTERN}$"
)
_RELEASE_TEMP_PATTERN = re.compile(
    rf"^{re.escape(_RELEASE_STAGE_PREFIX)}{_TOKEN_PATTERN}$"
)
_ATOMIC_TEMP_PATTERN = re.compile(
    r"^\.(?:extension\.mjs|\.copilot-command-ring-managed\.json)"
    rf"\.{_TOKEN_PATTERN}\.tmp$"
)
_REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
_TOKEN_BYTES = 16
_CREATE_ATTEMPTS = 100


class AppExtensionDeployError(RuntimeError):
    """Raised when the App extension cannot be deployed safely."""


@dataclass(frozen=True)
class AppExtensionDeployment:
    """Result of a successful App extension deployment."""

    target: Path
    bridge_sha256: str
    mode: str


@dataclass(frozen=True)
class _ReleaseInstallState:
    path: Path
    created: bool
    backup: Path | None


@dataclass(frozen=True)
class _InitialTargetContents:
    extension: bytes
    marker: bytes
    bridge: bytes
    bridge_sha256: str


@dataclass(frozen=True)
class _OwnedTargetState:
    marker_path: Path
    loader_path: Path
    releases_dir: Path
    previous_marker: bytes
    previous_loader: bytes | None
    marker_content: bytes
    mode: str


@dataclass
class _OwnedRollbackState:
    release: _ReleaseInstallState | None = None
    releases_dir_created: bool = False
    loader_replaced: bool = False
    marker_replaced: bool = False


def default_extension_target() -> Path:
    """Return the marker-owned user extension target."""
    copilot_home = os.environ.get("COPILOT_HOME")
    root = Path(copilot_home).expanduser() if copilot_home else Path.home() / ".copilot"
    return root / "extensions" / EXTENSION_NAME


def _path_info(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AppExtensionDeployError(f"Cannot inspect managed path {path}: {exc}") from exc


def _is_link_or_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & _REPARSE_ATTRIBUTE)


def _require_safe_path(
    path: Path,
    *,
    kind: str,
    allow_missing: bool = False,
) -> os.stat_result | None:
    info = _path_info(path)
    if info is None:
        if allow_missing:
            return None
        raise AppExtensionDeployError(f"Managed {kind} path is missing: {path}")
    if _is_link_or_reparse(info):
        raise AppExtensionDeployError(
            f"Managed {kind} path is unsafe (link or reparse point): {path}"
        )
    expected = stat.S_ISDIR(info.st_mode) if kind == "directory" else stat.S_ISREG(info.st_mode)
    if not expected:
        raise AppExtensionDeployError(f"Managed {kind} path is unsafe: {path}")
    return info


def _read_regular_bytes(path: Path, *, allow_missing: bool = False) -> bytes | None:
    if _require_safe_path(path, kind="file", allow_missing=allow_missing) is None:
        return None
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AppExtensionDeployError(f"Cannot read managed file {path}: {exc}") from exc


def _validate_marker(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _MARKER_KEYS:
        raise AppExtensionDeployError("Invalid ownership marker: unexpected schema.")
    if (
        not isinstance(value["schema_version"], int)
        or isinstance(value["schema_version"], bool)
        or value["schema_version"] != SCHEMA_VERSION
        or value["owner"] != OWNER
        or value["extension"] != EXTENSION_NAME
    ):
        raise AppExtensionDeployError("Invalid ownership marker: owner or schema mismatch.")
    active_sha = value["active_bridge_sha256"]
    releases = value["tracked_releases"]
    mode = value["mode"]
    if not isinstance(active_sha, str) or not _HASH_PATTERN.fullmatch(active_sha):
        raise AppExtensionDeployError("Invalid ownership marker: active SHA is malformed.")
    if (
        not isinstance(releases, list)
        or not releases
        or any(
            not isinstance(release, str) or not _HASH_PATTERN.fullmatch(release)
            for release in releases
        )
        or len(set(releases)) != len(releases)
        or active_sha not in releases
    ):
        raise AppExtensionDeployError("Invalid ownership marker: tracked releases are malformed.")
    if mode not in {"probe", "forwarding"}:
        raise AppExtensionDeployError("Invalid ownership marker: mode is malformed.")
    return value


def _tracked_releases(marker: dict[str, object]) -> list[str]:
    raw_releases = marker["tracked_releases"]
    assert isinstance(raw_releases, list)
    releases: list[str] = []
    for release in raw_releases:
        assert isinstance(release, str)
        releases.append(release)
    return releases


def _read_marker(target: Path) -> dict[str, object]:
    marker_path = target / MARKER_NAME
    _require_safe_path(marker_path, kind="file")
    try:
        value = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AppExtensionDeployError(f"Invalid ownership marker at {marker_path}: {exc}") from exc
    return _validate_marker(value)


def _resource_bytes(name: str) -> bytes:
    try:
        return (
            importlib.resources.files("copilot_command_ring")
            .joinpath("copilot_app_extension", name)
            .read_bytes()
        )
    except (FileNotFoundError, OSError) as exc:
        raise AppExtensionDeployError(f"Packaged App extension asset is missing: {name}") from exc


def _write_synced(path: Path, content: bytes) -> None:
    _require_safe_path(path.parent, kind="directory")
    _require_safe_path(path, kind="file", allow_missing=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise AppExtensionDeployError(f"Cannot create managed file {path}: {exc}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _managed_token() -> str:
    return secrets.token_hex(_TOKEN_BYTES)


def _create_managed_directory(parent: Path, *, prefix: str) -> Path:
    _require_safe_path(parent, kind="directory")
    for _ in range(_CREATE_ATTEMPTS):
        path = parent / f"{prefix}{_managed_token()}"
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            continue
        except OSError as exc:
            raise AppExtensionDeployError(
                f"Cannot create managed temporary directory {path}: {exc}"
            ) from exc
        return path
    raise AppExtensionDeployError(
        f"Cannot allocate managed temporary directory beneath {parent}."
    )


def _create_atomic_file(path: Path) -> tuple[int, Path]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    for _ in range(_CREATE_ATTEMPTS):
        temporary = path.parent / f".{path.name}.{_managed_token()}.tmp"
        try:
            return os.open(temporary, flags, 0o600), temporary
        except FileExistsError:
            continue
        except OSError as exc:
            raise AppExtensionDeployError(
                f"Cannot create atomic temporary file {temporary}: {exc}"
            ) from exc
    raise AppExtensionDeployError(
        f"Cannot allocate atomic temporary file for {path}."
    )


def _atomic_write(path: Path, content: bytes) -> None:
    _require_safe_path(path.parent, kind="directory")
    _require_safe_path(path, kind="file", allow_missing=True)
    descriptor, temporary = _create_atomic_file(path)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        info = _path_info(temporary)
        if info is not None:
            if _is_link_or_reparse(info) or not stat.S_ISREG(info.st_mode):
                raise AppExtensionDeployError(f"Atomic temporary path became unsafe: {temporary}")
            temporary.unlink()


def _marker_bytes(bridge_sha256: str, mode: str) -> bytes:
    marker = {
        "schema_version": SCHEMA_VERSION,
        "owner": OWNER,
        "extension": EXTENSION_NAME,
        "active_bridge_sha256": bridge_sha256,
        "tracked_releases": [bridge_sha256],
        "mode": mode,
    }
    return (json.dumps(marker, indent=2) + "\n").encode()


def _verify_bridge(path: Path, expected_sha256: str) -> None:
    _require_safe_path(path, kind="file")
    try:
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise AppExtensionDeployError(f"Cannot verify staged bridge at {path}: {exc}") from exc
    if actual_sha256 != expected_sha256:
        raise AppExtensionDeployError(
            f"Bridge verification failed at {path}: expected {expected_sha256}, "
            f"found {actual_sha256}."
        )


@contextmanager
def _deployment_lock(target: Path) -> Iterator[None]:
    lock_path = target.parent / f".{EXTENSION_NAME}.copilot-command-ring.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except FileExistsError as exc:
        raise AppExtensionDeployError(
            f"App extension deployment lock already exists: {lock_path}"
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        info = _path_info(lock_path)
        if info is not None and not _is_link_or_reparse(info) and stat.S_ISREG(info.st_mode):
            lock_path.unlink()


def _install_release(
    releases_dir: Path, bridge: bytes, bridge_sha256: str
) -> _ReleaseInstallState:
    _require_safe_path(releases_dir, kind="directory")
    destination = releases_dir / bridge_sha256
    destination_info = _require_safe_path(
        destination, kind="directory", allow_missing=True
    )
    if destination_info is not None:
        bridge_path = destination / "bridge.mjs"
        bridge_info = _require_safe_path(bridge_path, kind="file", allow_missing=True)
        if bridge_info is not None:
            try:
                _verify_bridge(bridge_path, bridge_sha256)
            except AppExtensionDeployError:
                pass
            else:
                return _ReleaseInstallState(destination, False, None)

    staged = _create_managed_directory(
        releases_dir,
        prefix=_RELEASE_STAGE_PREFIX,
    )
    try:
        bridge_path = staged / "bridge.mjs"
        _write_synced(bridge_path, bridge)
        _verify_bridge(bridge_path, bridge_sha256)
        if destination_info is None:
            os.replace(staged, destination)
            return _ReleaseInstallState(destination, True, None)

        backup = _create_managed_directory(
            releases_dir,
            prefix=_RELEASE_BACKUP_PREFIX,
        )
        backup.rmdir()
        os.replace(destination, backup)
        try:
            os.replace(staged, destination)
        except Exception as replacement_error:
            try:
                os.replace(backup, destination)
            except Exception as restoration_error:
                raise AppExtensionDeployError(
                    "Release replacement failed and rollback was incomplete: "
                    f"could not restore {destination}: {restoration_error}"
                ) from replacement_error
            raise
        return _ReleaseInstallState(destination, False, backup)
    finally:
        if _path_info(staged) is not None:
            _require_safe_path(staged, kind="directory")
            shutil.rmtree(staged)


def _rollback_release(
    state: _ReleaseInstallState,
) -> None:
    if state.created and _path_info(state.path) is not None:
        _require_safe_path(state.path, kind="directory")
        shutil.rmtree(state.path)
    if state.backup is not None and _path_info(state.backup) is not None:
        _require_safe_path(state.backup, kind="directory")
        if _path_info(state.path) is not None:
            _require_safe_path(state.path, kind="directory")
            shutil.rmtree(state.path)
        os.replace(state.backup, state.path)


def _remove_known_artifact(path: Path, *, expected_kind: str) -> None:
    info = _path_info(path)
    if info is None or _is_link_or_reparse(info):
        return
    if expected_kind == "directory" and stat.S_ISDIR(info.st_mode):
        shutil.rmtree(path)
    elif expected_kind == "file" and stat.S_ISREG(info.st_mode):
        path.unlink()


def _cleanup_managed_temps(target: Path) -> None:
    for entry in target.parent.iterdir():
        if _STAGE_TEMP_PATTERN.fullmatch(entry.name):
            _remove_known_artifact(entry, expected_kind="directory")
    releases_dir = target / "releases"
    if _require_safe_path(releases_dir, kind="directory", allow_missing=True) is not None:
        for entry in releases_dir.iterdir():
            if _RELEASE_TEMP_PATTERN.fullmatch(entry.name):
                _remove_known_artifact(entry, expected_kind="directory")
    for entry in target.iterdir():
        if _ATOMIC_TEMP_PATTERN.fullmatch(entry.name):
            _remove_known_artifact(entry, expected_kind="file")


def _validate_owned_layout(target: Path, marker: dict[str, object]) -> None:
    _require_safe_path(target, kind="directory")
    _require_safe_path(target / MARKER_NAME, kind="file")
    _require_safe_path(target / "extension.mjs", kind="file", allow_missing=True)
    releases_dir = target / "releases"
    if _require_safe_path(releases_dir, kind="directory", allow_missing=True) is None:
        return
    for release in _tracked_releases(marker):
        release_dir = releases_dir / release
        if _require_safe_path(
            release_dir, kind="directory", allow_missing=True
        ) is not None:
            _require_safe_path(
                release_dir / "bridge.mjs", kind="file", allow_missing=True
            )


def _require_exact_entries(
    path: Path,
    expected: set[str],
    *,
    description: str,
) -> None:
    try:
        actual = {entry.name for entry in path.iterdir()}
    except OSError as exc:
        raise AppExtensionDeployError(
            f"Cannot inspect {description} entries at {path}: {exc}"
        ) from exc
    if actual != expected:
        unexpected = sorted(actual - expected)
        missing = sorted(expected - actual)
        details: list[str] = []
        if unexpected:
            details.append(f"unexpected entries: {', '.join(unexpected)}")
        if missing:
            details.append(f"missing entries: {', '.join(missing)}")
        raise AppExtensionDeployError(
            f"Cannot safely remove initial target {path}: {'; '.join(details)}."
        )


def _validate_new_target_for_removal(
    target: Path,
    *,
    contents: _InitialTargetContents,
) -> None:
    _require_safe_path(target, kind="directory")
    _require_exact_entries(
        target,
        {"extension.mjs", MARKER_NAME, "releases"},
        description="initial target",
    )
    releases_dir = target / "releases"
    _require_safe_path(releases_dir, kind="directory")
    _require_exact_entries(
        releases_dir,
        {contents.bridge_sha256},
        description="initial releases directory",
    )
    release_dir = releases_dir / contents.bridge_sha256
    _require_safe_path(release_dir, kind="directory")
    _require_exact_entries(
        release_dir,
        {"bridge.mjs"},
        description="initial active release",
    )

    bridge_path = release_dir / "bridge.mjs"
    expected_files = {
        target / "extension.mjs": contents.extension,
        target / MARKER_NAME: contents.marker,
        bridge_path: contents.bridge,
    }
    actual_bridge: bytes | None = None
    for path, expected in expected_files.items():
        actual = _read_regular_bytes(path)
        if actual != expected:
            raise AppExtensionDeployError(
                f"Cannot safely remove initial target {target}: "
                f"managed bytes changed at {path}."
            )
        if path == bridge_path:
            actual_bridge = actual
    assert actual_bridge is not None
    actual_sha256 = hashlib.sha256(actual_bridge).hexdigest()
    if actual_sha256 != contents.bridge_sha256:
        raise AppExtensionDeployError(
            f"Cannot safely remove initial target {target}: bridge hash changed."
        )


def _require_rollback_target_absent(target: Path, quarantine: Path) -> None:
    if _path_info(target) is not None:
        raise AppExtensionDeployError(
            f"Recreated target {target} detected during rollback cleanup; "
            f"recovery data remains at {quarantine}."
        )


def _remove_exact_rollback_file(
    path: Path,
    expected: bytes,
    *,
    target: Path,
    quarantine: Path,
    expected_sha256: str | None = None,
) -> None:
    _require_rollback_target_absent(target, quarantine)
    actual = _read_regular_bytes(path)
    _require_rollback_target_absent(target, quarantine)
    if actual != expected:
        raise AppExtensionDeployError(
            f"Cannot remove rollback quarantine file with changed bytes: {path}"
        )
    assert actual is not None
    if (
        expected_sha256 is not None
        and hashlib.sha256(actual).hexdigest() != expected_sha256
    ):
        raise AppExtensionDeployError(
            f"Cannot remove rollback quarantine file with changed hash: {path}"
        )
    _require_rollback_target_absent(target, quarantine)
    try:
        path.unlink()
    except OSError as exc:
        _require_rollback_target_absent(target, quarantine)
        raise AppExtensionDeployError(
            f"Cannot remove exact rollback quarantine file {path}: {exc}"
        ) from exc
    _require_rollback_target_absent(target, quarantine)


def _remove_exact_rollback_directory(
    path: Path,
    *,
    target: Path,
    quarantine: Path,
) -> None:
    _require_rollback_target_absent(target, quarantine)
    _require_safe_path(path, kind="directory")
    _require_rollback_target_absent(target, quarantine)
    try:
        path.rmdir()
    except OSError as exc:
        _require_rollback_target_absent(target, quarantine)
        raise AppExtensionDeployError(
            f"Cannot remove exact rollback quarantine directory {path}: {exc}"
        ) from exc
    _require_rollback_target_absent(target, quarantine)


def _remove_validated_rollback_quarantine(
    target: Path,
    quarantine: Path,
    *,
    contents: _InitialTargetContents,
) -> None:
    release_dir = quarantine / "releases" / contents.bridge_sha256
    _require_rollback_target_absent(target, quarantine)
    _remove_exact_rollback_file(
        release_dir / "bridge.mjs",
        contents.bridge,
        target=target,
        quarantine=quarantine,
        expected_sha256=contents.bridge_sha256,
    )
    _remove_exact_rollback_file(
        quarantine / "extension.mjs",
        contents.extension,
        target=target,
        quarantine=quarantine,
    )
    _remove_exact_rollback_file(
        quarantine / MARKER_NAME,
        contents.marker,
        target=target,
        quarantine=quarantine,
    )
    _remove_exact_rollback_directory(
        release_dir,
        target=target,
        quarantine=quarantine,
    )
    _remove_exact_rollback_directory(
        quarantine / "releases",
        target=target,
        quarantine=quarantine,
    )
    _remove_exact_rollback_directory(
        quarantine,
        target=target,
        quarantine=quarantine,
    )
    _require_rollback_target_absent(target, quarantine)


def _rollback_new_target(
    target: Path,
    *,
    contents: _InitialTargetContents,
) -> None:
    _validate_new_target_for_removal(
        target,
        contents=contents,
    )
    quarantine = _create_managed_directory(
        target.parent,
        prefix=_INITIAL_ROLLBACK_PREFIX,
    )
    quarantine.rmdir()
    os.replace(target, quarantine)
    try:
        _validate_new_target_for_removal(
            quarantine,
            contents=contents,
        )
    except Exception as validation_error:
        try:
            if _path_info(target) is not None:
                raise AppExtensionDeployError(
                    f"Initial target path was recreated while {quarantine} "
                    "held rollback recovery data."
                ) from validation_error
            os.replace(quarantine, target)
        except Exception as restoration_error:
            raise AppExtensionDeployError(
                "Initial target changed during rollback and recovery was incomplete: "
                f"{restoration_error}; recovery data remains at {quarantine}."
            ) from validation_error
        raise
    _remove_validated_rollback_quarantine(
        target,
        quarantine,
        contents=contents,
    )


def _deploy_new_target(
    target: Path,
    extension: bytes,
    bridge: bytes,
    bridge_sha256: str,
) -> None:
    staged = _create_managed_directory(
        target.parent,
        prefix=_STAGE_PREFIX,
    )
    marker_content = _marker_bytes(bridge_sha256, "probe")
    target_renamed = False
    try:
        releases_dir = staged / "releases"
        releases_dir.mkdir()
        _install_release(releases_dir, bridge, bridge_sha256)
        _write_synced(staged / "extension.mjs", extension)
        _atomic_write(staged / MARKER_NAME, marker_content)
        if _read_marker(staged) != json.loads(marker_content):
            raise AppExtensionDeployError("Initial marker read-back verification failed.")
        os.replace(staged, target)
        target_renamed = True
        if _read_marker(target) != json.loads(marker_content):
            raise AppExtensionDeployError("Initial marker read-back verification failed.")
        _verify_bridge(target / "releases" / bridge_sha256 / "bridge.mjs", bridge_sha256)
        _cleanup_managed_temps(target)
    except Exception as original_error:
        if target_renamed:
            try:
                _rollback_new_target(
                    target,
                    contents=_InitialTargetContents(
                        extension,
                        marker_content,
                        bridge,
                        bridge_sha256,
                    ),
                )
            except Exception as rollback_error:
                raise AppExtensionDeployError(
                    "Initial deployment failed and rollback was incomplete: "
                    f"{rollback_error}"
                ) from original_error
        raise
    finally:
        if _path_info(staged) is not None:
            _require_safe_path(staged, kind="directory")
            shutil.rmtree(staged)


def _owned_target_state(
    target: Path,
    previous_marker: dict[str, object],
    bridge_sha256: str,
    *,
    activate_forwarding: bool,
) -> _OwnedTargetState:
    marker_path = target / MARKER_NAME
    loader_path = target / "extension.mjs"
    previous_bytes = _read_regular_bytes(marker_path)
    previous_loader = _read_regular_bytes(loader_path, allow_missing=True)
    assert previous_bytes is not None
    releases_dir = target / "releases"
    mode = (
        "forwarding"
        if activate_forwarding or previous_marker["mode"] == "forwarding"
        else "probe"
    )
    marker_content = _marker_bytes(bridge_sha256, mode)
    return _OwnedTargetState(
        marker_path,
        loader_path,
        releases_dir,
        previous_bytes,
        previous_loader,
        marker_content,
        mode,
    )


def _rollback_owned_target(
    target: _OwnedTargetState,
    rollback: _OwnedRollbackState,
) -> list[Exception]:
    rollback_errors: list[Exception] = []
    if rollback.marker_replaced:
        try:
            _atomic_write(target.marker_path, target.previous_marker)
        # Rollback must aggregate every filesystem failure without masking the original.
        except Exception as exc:  # pylint: disable=broad-exception-caught
            rollback_errors.append(exc)
    if rollback.loader_replaced:
        try:
            if target.previous_loader is None:
                _require_safe_path(target.loader_path, kind="file")
                target.loader_path.unlink()
            else:
                _atomic_write(target.loader_path, target.previous_loader)
        # Rollback must aggregate every filesystem failure without masking the original.
        except Exception as exc:  # pylint: disable=broad-exception-caught
            rollback_errors.append(exc)
    if rollback.release is not None:
        try:
            _rollback_release(rollback.release)
        # Rollback must aggregate every filesystem failure without masking the original.
        except Exception as exc:  # pylint: disable=broad-exception-caught
            rollback_errors.append(exc)
    if rollback.releases_dir_created and _path_info(target.releases_dir) is not None:
        try:
            _require_safe_path(target.releases_dir, kind="directory")
            target.releases_dir.rmdir()
        # Rollback must aggregate every filesystem failure without masking the original.
        except Exception as exc:  # pylint: disable=broad-exception-caught
            rollback_errors.append(exc)
    return rollback_errors


def _finalize_owned_target(
    target: Path,
    state: _OwnedTargetState,
    release_state: _ReleaseInstallState,
    previous_marker: dict[str, object],
    bridge_sha256: str,
) -> None:
    if release_state.backup is not None:
        _require_safe_path(release_state.backup, kind="directory")
        shutil.rmtree(release_state.backup)

    for release in _tracked_releases(previous_marker):
        if release == bridge_sha256:
            continue
        inactive = state.releases_dir / release
        if _require_safe_path(inactive, kind="directory", allow_missing=True) is not None:
            shutil.rmtree(inactive)
    _cleanup_managed_temps(target)


def _deploy_owned_target(
    target: Path,
    previous_marker: dict[str, object],
    extension: bytes,
    bridge: bytes,
    *,
    activate_forwarding: bool,
) -> str:
    bridge_sha256 = hashlib.sha256(bridge).hexdigest()
    state = _owned_target_state(
        target,
        previous_marker,
        bridge_sha256,
        activate_forwarding=activate_forwarding,
    )
    rollback = _OwnedRollbackState()
    try:
        if (
            _require_safe_path(
                state.releases_dir, kind="directory", allow_missing=True
            )
            is None
        ):
            state.releases_dir.mkdir()
            rollback.releases_dir_created = True
        rollback.release = _install_release(state.releases_dir, bridge, bridge_sha256)
        _atomic_write(state.loader_path, extension)
        rollback.loader_replaced = True
        _atomic_write(state.marker_path, state.marker_content)
        rollback.marker_replaced = True
        if _read_marker(target) != json.loads(state.marker_content):
            raise AppExtensionDeployError("Marker read-back verification failed.")
    except Exception as original_error:
        rollback_errors = _rollback_owned_target(state, rollback)
        if rollback_errors:
            details = "; ".join(str(error) for error in rollback_errors)
            raise AppExtensionDeployError(
                f"Deployment failed and rollback was incomplete: {details}"
            ) from original_error
        raise

    assert rollback.release is not None
    _finalize_owned_target(
        target,
        state,
        rollback.release,
        previous_marker,
        bridge_sha256,
    )
    return state.mode


def deploy_app_extension(
    *,
    target: Path | None = None,
    force: bool = False,
    activate_forwarding: bool = False,
) -> AppExtensionDeployment:
    """Deploy or refresh the marker-owned App extension.

    ``force`` intentionally never bypasses ownership validation. Forwarding
    activation is accepted only for an existing valid probe deployment.
    """
    del force
    requested_target = (target or default_extension_target()).expanduser()
    requested_info = _path_info(requested_target)
    if requested_info is not None and _is_link_or_reparse(requested_info):
        raise AppExtensionDeployError(
            f"App extension target is unsafe (link or reparse point): {requested_target}"
        )
    destination = Path(os.path.abspath(requested_target))
    destination.parent.mkdir(parents=True, exist_ok=True)

    extension = _resource_bytes("extension.mjs")
    bridge = _resource_bytes("bridge.mjs")
    bridge_sha256 = hashlib.sha256(bridge).hexdigest()

    with _deployment_lock(destination):
        previous_marker: dict[str, object] | None = None
        if _require_safe_path(
            destination, kind="directory", allow_missing=True
        ) is not None:
            marker_path = destination / MARKER_NAME
            if _path_info(marker_path) is None:
                raise AppExtensionDeployError(
                    f"Refusing to modify {destination} without a valid ownership marker."
                )
            previous_marker = _read_marker(destination)
            _validate_owned_layout(destination, previous_marker)
        elif activate_forwarding:
            raise AppExtensionDeployError(
                "Forwarding activation requires an existing owned probe deployment."
            )

        if previous_marker is None:
            _deploy_new_target(destination, extension, bridge, bridge_sha256)
            mode = "probe"
        else:
            mode = _deploy_owned_target(
                destination,
                previous_marker,
                extension,
                bridge,
                activate_forwarding=activate_forwarding,
            )

    return AppExtensionDeployment(destination, bridge_sha256, mode)
