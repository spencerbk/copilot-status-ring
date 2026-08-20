# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Tests for marker-owned GitHub Copilot App extension deployment."""

# These tests intentionally exercise private helpers to inject filesystem races.
# pylint: disable=protected-access

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
from copilot_command_ring import app_extension
from copilot_command_ring.app_extension import (
    AppExtensionDeployError,
    deploy_app_extension,
)


def _marker(target: Path) -> dict[str, object]:
    return json.loads(
        (target / ".copilot-command-ring-managed.json").read_text(encoding="utf-8")
    )


def _make_windows_junction(link: Path, target: Path) -> None:
    script = "New-Item -ItemType Junction -Path $env:RING_LINK -Target $env:RING_TARGET | Out-Null"
    environment = {
        **os.environ,
        "RING_LINK": str(link),
        "RING_TARGET": str(target),
    }
    subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_default_target_prefers_copilot_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prefer COPILOT_HOME when selecting the default extension target."""
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "copilot-home"))

    assert app_extension.default_extension_target() == (
        tmp_path / "copilot-home" / "extensions" / "copilot-app-status-ring"
    )


def test_initial_deploy_creates_probe_layout(tmp_path: Path) -> None:
    """Create the complete marker-owned probe layout on initial deployment."""
    target = tmp_path / "extensions" / "copilot-app-status-ring"

    result = deploy_app_extension(target=target)

    marker = _marker(target)
    bridge_sha = hashlib.sha256(
        (target / "releases" / result.bridge_sha256 / "bridge.mjs").read_bytes()
    ).hexdigest()
    assert result.target == target.resolve()
    assert result.mode == "probe"
    assert bridge_sha == result.bridge_sha256
    assert marker == {
        "schema_version": 1,
        "owner": "copilot-command-ring",
        "extension": "copilot-app-status-ring",
        "active_bridge_sha256": result.bridge_sha256,
        "tracked_releases": [result.bridge_sha256],
        "mode": "probe",
    }
    assert (target / "extension.mjs").is_file()


def test_deploy_is_idempotent_and_preserves_forwarding_mode(tmp_path: Path) -> None:
    """Keep one release and preserve forwarding mode across refreshes."""
    target = tmp_path / "copilot-app-status-ring"
    first = deploy_app_extension(target=target)
    activated = deploy_app_extension(target=target, activate_forwarding=True)
    refreshed = deploy_app_extension(target=target)

    assert first.bridge_sha256 == activated.bridge_sha256 == refreshed.bridge_sha256
    assert refreshed.mode == "forwarding"
    assert len(list((target / "releases").iterdir())) == 1


def test_deploy_recovers_safe_missing_loader_and_active_release(tmp_path: Path) -> None:
    """Restore missing managed artifacts in an otherwise owned layout."""
    target = tmp_path / "copilot-app-status-ring"
    first = deploy_app_extension(target=target)
    (target / "extension.mjs").unlink()
    active_release = target / "releases" / first.bridge_sha256
    app_extension.shutil.rmtree(active_release)

    recovered = deploy_app_extension(target=target)

    assert recovered.bridge_sha256 == first.bridge_sha256
    assert (target / "extension.mjs").is_file()
    assert (active_release / "bridge.mjs").is_file()


@pytest.mark.parametrize("bridge_state", ["missing", "corrupt"])
def test_deploy_recovers_safe_damaged_active_bridge(
    tmp_path: Path, bridge_state: str
) -> None:
    """Replace a missing or corrupt active bridge with packaged bytes."""
    target = tmp_path / "copilot-app-status-ring"
    first = deploy_app_extension(target=target)
    bridge_path = target / "releases" / first.bridge_sha256 / "bridge.mjs"
    if bridge_state == "missing":
        bridge_path.unlink()
    else:
        bridge_path.write_bytes(b"corrupt prior bridge")

    recovered = deploy_app_extension(target=target)

    assert recovered.bridge_sha256 == first.bridge_sha256
    assert hashlib.sha256(bridge_path.read_bytes()).hexdigest() == first.bridge_sha256


@pytest.mark.parametrize("bridge_state", ["missing", "corrupt"])
@pytest.mark.parametrize(
    "failed_prior_read",
    [".copilot-command-ring-managed.json", "extension.mjs"],
)
def test_prior_read_failure_does_not_replace_damaged_active_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bridge_state: str,
    failed_prior_read: str,
) -> None:
    """Leave a damaged release untouched when prior-state capture fails."""
    target = tmp_path / "copilot-app-status-ring"
    deployed = deploy_app_extension(target=target)
    release_path = target / "releases" / deployed.bridge_sha256
    bridge_path = release_path / "bridge.mjs"
    if bridge_state == "missing":
        bridge_path.unlink()
    else:
        bridge_path.write_bytes(b"corrupt prior bridge")
    prior_entries = {
        entry.name: entry.read_bytes() if entry.is_file() else None
        for entry in release_path.iterdir()
    }
    original_read_regular_bytes = app_extension._read_regular_bytes

    def fail_prior_read(path: Path, *, allow_missing: bool = False) -> bytes | None:
        if path.name == failed_prior_read:
            raise AppExtensionDeployError("injected prior-state read failure")
        return original_read_regular_bytes(path, allow_missing=allow_missing)

    monkeypatch.setattr(app_extension, "_read_regular_bytes", fail_prior_read)

    with pytest.raises(AppExtensionDeployError, match="injected prior-state read failure"):
        deploy_app_extension(target=target)

    assert {
        entry.name: entry.read_bytes() if entry.is_file() else None
        for entry in release_path.iterdir()
    } == prior_entries
    assert not list(
        release_path.parent.glob(".copilot-command-ring-release-backup-*")
    )
    assert not list(release_path.parent.glob(".copilot-command-ring-release-*"))


def test_release_replacement_reports_failed_restore_without_masking_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve recovery data and chain the original replacement failure."""
    target = tmp_path / "copilot-app-status-ring"
    deployed = deploy_app_extension(target=target)
    release_path = target / "releases" / deployed.bridge_sha256
    (release_path / "bridge.mjs").write_bytes(b"corrupt prior bridge")
    original_replace = app_extension.os.replace

    def fail_replacement_and_restore(source: Path, destination: Path) -> None:
        source = Path(source)
        destination = Path(destination)
        if destination == release_path:
            if source.name.startswith(
                ".copilot-command-ring-release-backup-"
            ):
                raise OSError("injected restoration failure")
            if source.name.startswith(".copilot-command-ring-release-"):
                raise OSError("injected replacement failure")
        original_replace(source, destination)

    monkeypatch.setattr(app_extension.os, "replace", fail_replacement_and_restore)

    with pytest.raises(
        AppExtensionDeployError,
        match="rollback was incomplete.*injected restoration failure",
    ) as error:
        deploy_app_extension(target=target)

    assert isinstance(error.value.__cause__, OSError)
    assert str(error.value.__cause__) == "injected replacement failure"
    backups = list(
        (target / "releases").glob(".copilot-command-ring-release-backup-*")
    )
    assert len(backups) == 1
    assert re.fullmatch(
        r"\.copilot-command-ring-release-backup-[0-9a-f]{32}",
        backups[0].name,
    )
    assert (backups[0] / "bridge.mjs").read_bytes() == b"corrupt prior bridge"


@pytest.mark.parametrize("force", [False, True])
def test_deploy_refuses_unowned_existing_target(tmp_path: Path, force: bool) -> None:
    """Refuse an existing unowned target even when force is requested."""
    target = tmp_path / "copilot-app-status-ring"
    target.mkdir()
    (target / "someone-elses-file").write_text("keep", encoding="utf-8")

    with pytest.raises(AppExtensionDeployError, match="valid ownership marker"):
        deploy_app_extension(target=target, force=force)

    assert (target / "someone-elses-file").read_text(encoding="utf-8") == "keep"


def test_deploy_refuses_invalid_marker_without_changing_it(tmp_path: Path) -> None:
    """Reject and preserve an invalid ownership marker."""
    target = tmp_path / "copilot-app-status-ring"
    target.mkdir()
    marker_path = target / ".copilot-command-ring-managed.json"
    marker_path.write_text('{"owner":"copilot-command-ring"}', encoding="utf-8")

    with pytest.raises(AppExtensionDeployError, match="Invalid ownership marker"):
        deploy_app_extension(target=target, force=True)

    assert marker_path.read_text(encoding="utf-8") == '{"owner":"copilot-command-ring"}'


def test_deploy_refuses_concurrent_lock(tmp_path: Path) -> None:
    """Reject deployment while another deployment lock exists."""
    target = tmp_path / "copilot-app-status-ring"
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.parent / ".copilot-app-status-ring.copilot-command-ring.lock"
    lock_path.write_text("held", encoding="utf-8")

    with pytest.raises(AppExtensionDeployError, match="deployment lock"):
        deploy_app_extension(target=target)

    assert lock_path.read_text(encoding="utf-8") == "held"


def test_activation_requires_existing_owned_probe(tmp_path: Path) -> None:
    """Require an existing owned probe before forwarding activation."""
    target = tmp_path / "copilot-app-status-ring"

    with pytest.raises(AppExtensionDeployError, match="probe deployment"):
        deploy_app_extension(target=target, activate_forwarding=True)


def test_unknown_files_are_preserved(tmp_path: Path) -> None:
    """Preserve unknown files and release directories during refresh."""
    target = tmp_path / "copilot-app-status-ring"
    deployed = deploy_app_extension(target=target)
    unknown_root = target / "operator-note.txt"
    unknown_release = target / "releases" / ("f" * 64)
    unknown_root.write_text("keep", encoding="utf-8")
    unknown_release.mkdir()
    (unknown_release / "other.txt").write_text("keep", encoding="utf-8")

    deploy_app_extension(target=target, force=True)

    assert unknown_root.read_text(encoding="utf-8") == "keep"
    assert (unknown_release / "other.txt").read_text(encoding="utf-8") == "keep"
    assert (target / "releases" / deployed.bridge_sha256).is_dir()


def test_verification_failure_restores_previous_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Restore the previous marker and release after verification failure."""
    target = tmp_path / "copilot-app-status-ring"
    first = deploy_app_extension(target=target)
    old_marker_bytes = (
        target / ".copilot-command-ring-managed.json"
    ).read_bytes()
    original_resource_bytes = app_extension._resource_bytes
    original_read_marker = app_extension._read_marker
    calls = 0

    def changed_resource(name: str) -> bytes:
        content = original_resource_bytes(name)
        return content + b"\n// changed release\n" if name == "bridge.mjs" else content

    def fail_post_replace(path: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AppExtensionDeployError("injected read-back failure")
        return original_read_marker(path)

    monkeypatch.setattr(app_extension, "_resource_bytes", changed_resource)
    monkeypatch.setattr(app_extension, "_read_marker", fail_post_replace)
    changed_sha = hashlib.sha256(changed_resource("bridge.mjs")).hexdigest()

    with pytest.raises(AppExtensionDeployError, match="injected read-back failure"):
        deploy_app_extension(target=target)

    assert (
        target / ".copilot-command-ring-managed.json"
    ).read_bytes() == old_marker_bytes
    assert (target / "releases" / first.bridge_sha256 / "bridge.mjs").is_file()
    assert not (target / "releases" / changed_sha).exists()


def test_verification_failure_restores_previous_marker_and_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Restore both prior root files when post-write verification fails."""
    target = tmp_path / "copilot-app-status-ring"
    first = deploy_app_extension(target=target)
    marker_path = target / ".copilot-command-ring-managed.json"
    loader_path = target / "extension.mjs"
    old_marker_bytes = marker_path.read_bytes()
    old_loader_bytes = loader_path.read_bytes()
    original_resource_bytes = app_extension._resource_bytes
    original_read_marker = app_extension._read_marker
    calls = 0

    def changed_resource(name: str) -> bytes:
        return original_resource_bytes(name) + f"\n// changed {name}\n".encode()

    def fail_post_replace(path: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AppExtensionDeployError("injected read-back failure")
        return original_read_marker(path)

    monkeypatch.setattr(app_extension, "_resource_bytes", changed_resource)
    monkeypatch.setattr(app_extension, "_read_marker", fail_post_replace)
    changed_sha = hashlib.sha256(changed_resource("bridge.mjs")).hexdigest()

    with pytest.raises(AppExtensionDeployError, match="injected read-back failure"):
        deploy_app_extension(target=target)

    assert marker_path.read_bytes() == old_marker_bytes
    assert loader_path.read_bytes() == old_loader_bytes
    assert (target / "releases" / first.bridge_sha256 / "bridge.mjs").is_file()
    assert not (target / "releases" / changed_sha).exists()


def test_verification_failure_removes_new_loader_when_previously_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove a newly written loader when rollback had no prior loader."""
    target = tmp_path / "copilot-app-status-ring"
    deploy_app_extension(target=target)
    (target / "extension.mjs").unlink()
    original_read_marker = app_extension._read_marker
    calls = 0

    def fail_post_replace(path: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AppExtensionDeployError("injected read-back failure")
        return original_read_marker(path)

    monkeypatch.setattr(app_extension, "_read_marker", fail_post_replace)

    with pytest.raises(AppExtensionDeployError, match="injected read-back failure"):
        deploy_app_extension(target=target)

    assert not (target / "extension.mjs").exists()


def test_initial_marker_readback_failure_removes_exact_new_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove the exact initial target when marker read-back fails."""
    target = tmp_path / "extensions" / "copilot-app-status-ring"
    original_read_marker = app_extension._read_marker

    def fail_post_rename(path: Path) -> dict[str, object]:
        if path == target:
            raise AppExtensionDeployError("injected initial marker read-back failure")
        return original_read_marker(path)

    monkeypatch.setattr(app_extension, "_read_marker", fail_post_rename)

    with pytest.raises(
        AppExtensionDeployError, match="injected initial marker read-back failure"
    ):
        deploy_app_extension(target=target)

    lock_path = target.parent / ".copilot-app-status-ring.copilot-command-ring.lock"
    assert not target.exists()
    assert not lock_path.exists()

    monkeypatch.setattr(app_extension, "_read_marker", original_read_marker)
    assert deploy_app_extension(target=target).mode == "probe"


def test_initial_bridge_verification_failure_removes_exact_new_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove the exact initial target when bridge verification fails."""
    target = tmp_path / "extensions" / "copilot-app-status-ring"
    original_verify_bridge = app_extension._verify_bridge

    def fail_post_rename(path: Path, expected_sha256: str) -> None:
        if target in path.parents:
            raise AppExtensionDeployError("injected initial bridge verification failure")
        original_verify_bridge(path, expected_sha256)

    monkeypatch.setattr(app_extension, "_verify_bridge", fail_post_rename)

    with pytest.raises(
        AppExtensionDeployError, match="injected initial bridge verification failure"
    ):
        deploy_app_extension(target=target)

    lock_path = target.parent / ".copilot-app-status-ring.copilot-command-ring.lock"
    assert not target.exists()
    assert not lock_path.exists()

    monkeypatch.setattr(app_extension, "_verify_bridge", original_verify_bridge)
    assert deploy_app_extension(target=target).mode == "probe"


def test_initial_rollback_preserves_target_with_unknown_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve a target changed before initial rollback validation."""
    target = tmp_path / "extensions" / "copilot-app-status-ring"
    unknown = target / "concurrent-operator-data"
    original_read_marker = app_extension._read_marker

    def add_unknown_then_fail(path: Path) -> dict[str, object]:
        if path == target:
            unknown.write_text("preserve", encoding="utf-8")
            raise AppExtensionDeployError("injected initial marker read-back failure")
        return original_read_marker(path)

    monkeypatch.setattr(app_extension, "_read_marker", add_unknown_then_fail)

    with pytest.raises(
        AppExtensionDeployError,
        match="rollback was incomplete.*concurrent-operator-data",
    ) as error:
        deploy_app_extension(target=target)

    assert isinstance(error.value.__cause__, AppExtensionDeployError)
    assert unknown.read_text(encoding="utf-8") == "preserve"
    assert not (
        target.parent / ".copilot-app-status-ring.copilot-command-ring.lock"
    ).exists()


def test_initial_rollback_preserves_target_recreated_after_quarantine_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve a concurrently recreated target and quarantined recovery data."""
    target = tmp_path / "extensions" / "copilot-app-status-ring"
    recreated_sentinel = target / "recreated-target-sentinel"
    original_read_marker = app_extension._read_marker
    original_validate = app_extension._validate_new_target_for_removal
    quarantine: Path | None = None

    def fail_post_rename(path: Path) -> dict[str, object]:
        if path == target:
            raise AppExtensionDeployError("injected initial marker read-back failure")
        return original_read_marker(path)

    def recreate_target_after_quarantine_validation(
        path: Path, **expected: object
    ) -> None:
        nonlocal quarantine
        original_validate(path, **expected)
        if path != target and quarantine is None:
            quarantine = path
            target.mkdir()
            recreated_sentinel.write_text("preserve target", encoding="utf-8")

    monkeypatch.setattr(app_extension, "_read_marker", fail_post_rename)
    monkeypatch.setattr(
        app_extension,
        "_validate_new_target_for_removal",
        recreate_target_after_quarantine_validation,
    )

    with pytest.raises(
        AppExtensionDeployError,
        match="rollback was incomplete.*[Rr]ecreated target",
    ) as error:
        deploy_app_extension(target=target)

    assert isinstance(error.value.__cause__, AppExtensionDeployError)
    assert str(error.value.__cause__) == "injected initial marker read-back failure"
    assert recreated_sentinel.read_text(encoding="utf-8") == "preserve target"
    assert quarantine is not None
    assert (quarantine / "extension.mjs").is_file()
    assert (quarantine / app_extension.MARKER_NAME).is_file()
    assert list((quarantine / "releases").glob("*/bridge.mjs"))
    assert not (
        target.parent / ".copilot-app-status-ring.copilot-command-ring.lock"
    ).exists()

    recreated_sentinel.unlink()
    target.rmdir()
    app_extension.shutil.rmtree(quarantine)
    monkeypatch.setattr(app_extension, "_read_marker", original_read_marker)
    monkeypatch.setattr(
        app_extension,
        "_validate_new_target_for_removal",
        original_validate,
    )
    assert deploy_app_extension(target=target).mode == "probe"


def test_initial_rollback_preserves_quarantine_content_added_after_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve quarantine data changed after rollback validation."""
    target = tmp_path / "extensions" / "copilot-app-status-ring"
    original_read_marker = app_extension._read_marker
    original_validate = app_extension._validate_new_target_for_removal
    quarantine: Path | None = None
    quarantine_sentinel: Path | None = None

    def fail_post_rename(path: Path) -> dict[str, object]:
        if path == target:
            raise AppExtensionDeployError("injected initial marker read-back failure")
        return original_read_marker(path)

    def add_quarantine_content_after_validation(
        path: Path, **expected: object
    ) -> None:
        nonlocal quarantine, quarantine_sentinel
        original_validate(path, **expected)
        if path != target and quarantine is None:
            quarantine = path
            quarantine_sentinel = path / "concurrent-quarantine-sentinel"
            quarantine_sentinel.write_text(
                "preserve quarantine",
                encoding="utf-8",
            )

    monkeypatch.setattr(app_extension, "_read_marker", fail_post_rename)
    monkeypatch.setattr(
        app_extension,
        "_validate_new_target_for_removal",
        add_quarantine_content_after_validation,
    )

    with pytest.raises(
        AppExtensionDeployError,
        match="rollback was incomplete.*quarantine",
    ) as error:
        deploy_app_extension(target=target)

    assert isinstance(error.value.__cause__, AppExtensionDeployError)
    assert str(error.value.__cause__) == "injected initial marker read-back failure"
    assert quarantine is not None
    assert quarantine_sentinel is not None
    assert quarantine_sentinel.read_text(encoding="utf-8") == "preserve quarantine"
    assert quarantine.is_dir()
    assert not (
        target.parent / ".copilot-app-status-ring.copilot-command-ring.lock"
    ).exists()

    app_extension.shutil.rmtree(quarantine)
    monkeypatch.setattr(app_extension, "_read_marker", original_read_marker)
    monkeypatch.setattr(
        app_extension,
        "_validate_new_target_for_removal",
        original_validate,
    )
    assert deploy_app_extension(target=target).mode == "probe"


def test_successful_update_cleans_only_tracked_inactive_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove only marker-tracked inactive releases after an update."""
    target = tmp_path / "copilot-app-status-ring"
    first = deploy_app_extension(target=target)
    unknown_release = target / "releases" / ("f" * 64)
    unknown_release.mkdir()
    (unknown_release / "unknown.txt").write_text("keep", encoding="utf-8")
    original_resource_bytes = app_extension._resource_bytes

    def changed_resource(name: str) -> bytes:
        content = original_resource_bytes(name)
        return content + b"\n// changed release\n" if name == "bridge.mjs" else content

    monkeypatch.setattr(app_extension, "_resource_bytes", changed_resource)

    updated = deploy_app_extension(target=target)

    assert updated.bridge_sha256 != first.bridge_sha256
    assert not (target / "releases" / first.bridge_sha256).exists()
    assert (target / "releases" / updated.bridge_sha256 / "bridge.mjs").is_file()
    assert (unknown_release / "unknown.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(os.name == "nt", reason="POSIX symbolic-link behavior")
@pytest.mark.parametrize(
    "managed_path",
    [
        ".copilot-command-ring-managed.json",
        "extension.mjs",
        "releases",
        "active-release",
        "bridge.mjs",
    ],
)
def test_deploy_refuses_posix_symlinks_in_managed_paths(
    tmp_path: Path, managed_path: str
) -> None:
    """Reject symbolic links at every managed POSIX path."""
    target = tmp_path / "copilot-app-status-ring"
    deployed = deploy_app_extension(target=target)
    active_release = target / "releases" / deployed.bridge_sha256
    paths = {
        ".copilot-command-ring-managed.json": target
        / ".copilot-command-ring-managed.json",
        "extension.mjs": target / "extension.mjs",
        "releases": target / "releases",
        "active-release": active_release,
        "bridge.mjs": active_release / "bridge.mjs",
    }
    attacked = paths[managed_path]
    saved = attacked.with_name(f"{attacked.name}.saved")
    attacked.rename(saved)
    attacked.symlink_to(saved, target_is_directory=saved.is_dir())

    with pytest.raises(AppExtensionDeployError, match="unsafe"):
        deploy_app_extension(target=target)

    assert attacked.is_symlink()
    assert saved.exists()


def test_deploy_refuses_symlink_target(tmp_path: Path) -> None:
    """Reject a symbolic link used as the deployment target."""
    real_target = tmp_path / "real-target"
    real_target.mkdir()
    linked_target = tmp_path / "copilot-app-status-ring"
    try:
        linked_target.symlink_to(real_target, target_is_directory=True)
    except OSError:
        if os.name == "nt":
            pytest.skip(
                "Windows symbolic links are unavailable; junction test covers reparse paths"
            )
        raise

    with pytest.raises(AppExtensionDeployError, match="unsafe|symlink"):
        deploy_app_extension(target=linked_target)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_deploy_refuses_windows_junction_target(tmp_path: Path) -> None:
    """Reject a Windows junction used as the deployment target."""
    real_target = tmp_path / "real-target"
    real_target.mkdir()
    junction = tmp_path / "copilot-app-status-ring"
    _make_windows_junction(junction, real_target)
    attributes = junction.lstat().st_file_attributes
    assert attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT

    with pytest.raises(AppExtensionDeployError, match="unsafe|reparse"):
        deploy_app_extension(target=junction)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
@pytest.mark.parametrize("managed_path", ["releases", "active-release"])
def test_deploy_refuses_windows_junction_managed_directory(
    tmp_path: Path, managed_path: str
) -> None:
    """Reject Windows junctions at managed directory paths."""
    target = tmp_path / "copilot-app-status-ring"
    deployed = deploy_app_extension(target=target)
    attacked = (
        target / "releases"
        if managed_path == "releases"
        else target / "releases" / deployed.bridge_sha256
    )
    saved = attacked.with_name(f"{attacked.name}.saved")
    attacked.rename(saved)
    _make_windows_junction(attacked, saved)

    with pytest.raises(AppExtensionDeployError, match="unsafe|reparse"):
        deploy_app_extension(target=target)

    assert attacked.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    assert saved.is_dir()


def test_deploy_uses_same_filesystem_staging_and_atomic_replacements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage beside destinations and atomically replace managed paths."""
    target = tmp_path / "extensions" / "copilot-app-status-ring"
    target.parent.mkdir()
    original_replace = app_extension.os.replace
    replacements: list[tuple[Path, Path]] = []

    def record_replace(source: Path, destination: Path) -> None:
        replacements.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr(app_extension.os, "replace", record_replace)

    deployed = deploy_app_extension(target=target)

    outer_stage, final_target = replacements[-1]
    assert final_target == target
    assert outer_stage.parent == target.parent
    assert re.fullmatch(
        r"\.copilot-app-status-ring\.stage-[0-9a-f]{32}",
        outer_stage.name,
    )
    release_replacements = [
        (source, destination)
        for source, destination in replacements
        if destination.name == deployed.bridge_sha256
    ]
    assert len(release_replacements) == 1
    release_stage, release_destination = release_replacements[0]
    assert release_stage.parent == release_destination.parent
    assert release_destination.parent == outer_stage / "releases"
    assert re.fullmatch(
        r"\.copilot-command-ring-release-[0-9a-f]{32}",
        release_stage.name,
    )
    marker_sources = [
        source
        for source, destination in replacements
        if destination.name == ".copilot-command-ring-managed.json"
    ]
    assert marker_sources
    assert all(
        re.fullmatch(
            r"\.\.copilot-command-ring-managed\.json\.[0-9a-f]{32}\.tmp",
            source.name,
        )
        for source in marker_sources
    )


def test_owned_deploy_atomically_replaces_loader_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Atomically replace both root files in an owned deployment."""
    target = tmp_path / "copilot-app-status-ring"
    deploy_app_extension(target=target)
    original_replace = app_extension.os.replace
    replacements: list[tuple[Path, Path]] = []

    def record_replace(source: Path, destination: Path) -> None:
        replacements.append((Path(source), Path(destination)))
        original_replace(source, destination)

    monkeypatch.setattr(app_extension.os, "replace", record_replace)

    deploy_app_extension(target=target)

    atomic_destinations = {
        destination.name: source
        for source, destination in replacements
        if destination.parent == target
    }
    assert set(atomic_destinations) == {
        "extension.mjs",
        ".copilot-command-ring-managed.json",
    }
    assert atomic_destinations["extension.mjs"].parent == target
    assert atomic_destinations["extension.mjs"].name.startswith(".extension.mjs.")
    marker_temp = atomic_destinations[".copilot-command-ring-managed.json"]
    assert marker_temp.parent == target
    assert marker_temp.name.startswith("..copilot-command-ring-managed.json.")


# The explicit near-match matrix keeps each preserved artifact independently asserted.
# pylint: disable-next=too-many-locals
def test_successful_deploy_cleans_only_recognized_safe_temp_artifacts(
    tmp_path: Path
) -> None:
    """Clean exact managed temp names while preserving near matches."""
    target = tmp_path / "extensions" / "copilot-app-status-ring"
    deployed = deploy_app_extension(target=target)
    token = "a" * 32
    known_stage = target.parent / f".copilot-app-status-ring.stage-{token}"
    unknown_stage = target.parent / ".copilot-app-status-ring.stage"
    operator_stage = (
        target.parent / ".copilot-app-status-ring.stage-operator-data"
    )
    short_stage = target.parent / f".copilot-app-status-ring.stage-{token[:-1]}"
    uppercase_token = "B" * 32
    uppercase_stage = (
        target.parent / f".copilot-app-status-ring.stage-{uppercase_token}"
    )
    known_release_temp = (
        target / "releases" / f".copilot-command-ring-release-{token}"
    )
    unknown_release_temp = target / "releases" / ".copilot-command-ring-release"
    operator_release = (
        target / "releases" / ".copilot-command-ring-release-operator-data"
    )
    short_release = (
        target / "releases" / f".copilot-command-ring-release-{token[:-1]}"
    )
    backup_release = (
        target
        / "releases"
        / f".copilot-command-ring-release-backup-{token}"
    )
    uppercase_release = (
        target / "releases" / f".copilot-command-ring-release-{uppercase_token}"
    )
    known_loader_temp = target / f".extension.mjs.{token}.tmp"
    known_marker_temp = (
        target / f"..copilot-command-ring-managed.json.{token}.tmp"
    )
    unknown_atomic_temp = target / ".extension.mjs.operator.tmp"
    short_atomic_temp = target / f".extension.mjs.{token[:-1]}.tmp"
    uppercase_atomic_temp = target / f".extension.mjs.{uppercase_token}.tmp"
    for directory in (
        known_stage,
        unknown_stage,
        operator_stage,
        short_stage,
        uppercase_stage,
        known_release_temp,
        unknown_release_temp,
        operator_release,
        short_release,
        backup_release,
        uppercase_release,
    ):
        directory.mkdir()
    for file_path in (
        known_loader_temp,
        known_marker_temp,
        unknown_atomic_temp,
        short_atomic_temp,
        uppercase_atomic_temp,
    ):
        file_path.write_text("keep-or-clean", encoding="utf-8")

    deploy_app_extension(target=target)

    assert not known_stage.exists()
    assert not known_release_temp.exists()
    assert not known_loader_temp.exists()
    assert not known_marker_temp.exists()
    assert unknown_stage.is_dir()
    assert operator_stage.is_dir()
    assert short_stage.is_dir()
    assert uppercase_stage.is_dir()
    assert unknown_release_temp.is_dir()
    assert operator_release.is_dir()
    assert short_release.is_dir()
    assert backup_release.is_dir()
    assert uppercase_release.is_dir()
    assert unknown_atomic_temp.read_text(encoding="utf-8") == "keep-or-clean"
    assert short_atomic_temp.read_text(encoding="utf-8") == "keep-or-clean"
    assert uppercase_atomic_temp.read_text(encoding="utf-8") == "keep-or-clean"
    assert (target / "releases" / deployed.bridge_sha256).is_dir()


def test_successful_deploy_preserves_linked_recognized_temp_artifact(
    tmp_path: Path
) -> None:
    """Preserve a recognized temp path when it is a link or reparse point."""
    target = tmp_path / "extensions" / "copilot-app-status-ring"
    deploy_app_extension(target=target)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    linked_stage = target.parent / (
        ".copilot-app-status-ring.stage-" + ("b" * 32)
    )
    if os.name == "nt":
        _make_windows_junction(linked_stage, outside)
    else:
        linked_stage.symlink_to(outside, target_is_directory=True)

    deploy_app_extension(target=target)

    assert linked_stage.lstat()
    assert sentinel.read_text(encoding="utf-8") == "keep"
