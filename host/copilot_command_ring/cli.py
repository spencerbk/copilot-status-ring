# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""CLI entry point for the ``copilot-command-ring`` console script.

Subcommands
-----------
setup                 Install global hooks (all repos, one-time).
deploy <target-dir>   Deploy hooks into a specific repository.
deploy-app-extension  Deploy the marker-owned local App extension.
hook <event_name>     Handle a Copilot CLI hook event (called by deployed wrappers).
refresh               Reinstall the host and refresh the local App extension.
set-pixels <count>    Update the ring's LED count in the local config file.
doctor                Run a one-shot health check (config, ports, lock, ping).
"""

from __future__ import annotations

import argparse
import sys

from .app_extension import AppExtensionDeployError, deploy_app_extension


def main(argv: list[str] | None = None) -> None:  # pylint: disable=too-many-branches
    """Top-level CLI dispatcher."""
    parser = argparse.ArgumentParser(
        prog="copilot-command-ring",
        description=(
            "Copilot Command Ring - NeoPixel status ring for GitHub Copilot CLI "
            "and the local desktop App"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    # ── setup ──────────────────────────────────────────────────────────
    setup_parser = sub.add_parser(
        "setup",
        help="Install global hooks so the ring works in all repositories",
    )
    setup_parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh hooks and the owned App extension without prompting",
    )

    # ── deploy ─────────────────────────────────────────────────────────
    deploy_parser = sub.add_parser(
        "deploy",
        help="Deploy hooks into a specific repository",
    )
    deploy_parser.add_argument(
        "target_dir",
        help="Path to the root of the target repository",
    )
    deploy_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing hook files without prompting",
    )

    # ── deploy-app-extension ───────────────────────────────────────────
    app_extension_parser = sub.add_parser(
        "deploy-app-extension",
        help="Deploy or refresh the marker-owned GitHub Copilot App extension",
    )
    app_extension_parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh managed files (never bypasses ownership validation)",
    )
    app_extension_parser.add_argument(
        "--activate-forwarding",
        action="store_true",
        help="Activate only after different-repository exact desktop proof",
    )

    # ── setup-status-ring / wizard ──────────────────────────────────────
    setup_status_parser = sub.add_parser(
        "setup-status-ring",
        aliases=["wizard"],
        help="Guided setup for new Copilot Command Ring users",
    )
    from .setup_wizard import add_arguments as add_setup_status_arguments

    add_setup_status_arguments(setup_status_parser)

    # ── hook ───────────────────────────────────────────────────────────
    hook_parser = sub.add_parser(
        "hook",
        help="Handle a Copilot CLI hook event (called by deployed wrappers)",
    )
    hook_parser.add_argument(
        "event_name",
        help="The Copilot CLI event name (e.g. sessionStart, preToolUse)",
    )

    # ── refresh ────────────────────────────────────────────────────────
    refresh_parser = sub.add_parser(
        "refresh",
        help=(
            "Re-install / upgrade the host package into the wizard's venv, "
            "then deploy the newly installed App extension. Use after "
            "`git pull` or a release upgrade."
        ),
    )
    refresh_parser.add_argument(
        "--package-spec",
        default=None,
        help=(
            "Override the pip install spec (default: local clone path if "
            "detected, else the GitHub URL)."
        ),
    )
    refresh_parser.add_argument(
        "--venv-dir",
        default=None,
        help=(
            "Override the target virtual environment directory "
            "(default: <repo_root>/.venv when a clone is detected)."
        ),
    )

    # ── set-pixels ─────────────────────────────────────────────────────
    set_pixels_parser = sub.add_parser(
        "set-pixels",
        help="Update the ring's LED count in the local config file",
    )
    set_pixels_parser.add_argument(
        "count",
        type=int,
        help="Number of LEDs on the ring (e.g. 24)",
    )
    set_pixels_parser.add_argument(
        "--config-dir",
        help=(
            "Directory to start searching for "
            ".copilot-command-ring.local.json (default: cwd)"
        ),
    )

    # ── doctor ─────────────────────────────────────────────────────────
    doctor_parser = sub.add_parser(
        "doctor",
        help="Run a one-shot health check (config, ports, lock, ping)",
    )
    doctor_parser.add_argument(
        "--no-ping",
        action="store_true",
        help="Skip the test write to the device (still report config/ports/lock)",
    )
    doctor_parser.add_argument(
        "--config-dir",
        help=(
            "Directory to start searching for "
            ".copilot-command-ring.local.json (default: cwd)"
        ),
    )

    args = parser.parse_args(argv)

    if args.command == "setup":
        from .deploy import setup_global_hooks

        ok = setup_global_hooks(force=args.force)
        if ok:
            try:
                result = deploy_app_extension(force=args.force)
            except AppExtensionDeployError as exc:
                print(f"GitHub Copilot App extension deployment failed: {exc}", file=sys.stderr)
                ok = False
            else:
                print(
                    f"Deployed GitHub Copilot App extension to {result.target} "
                    f"(mode={result.mode}, bridge={result.bridge_sha256}).",
                    file=sys.stderr,
                )
        sys.exit(0 if ok else 1)

    elif args.command == "deploy":
        from .deploy import deploy_hooks

        ok = deploy_hooks(args.target_dir, force=args.force)
        sys.exit(0 if ok else 1)

    elif args.command == "deploy-app-extension":
        try:
            result = deploy_app_extension(
                force=args.force,
                activate_forwarding=args.activate_forwarding,
            )
        except AppExtensionDeployError as exc:
            print(f"GitHub Copilot App extension deployment failed: {exc}", file=sys.stderr)
            sys.exit(1)
        print(
            f"Deployed GitHub Copilot App extension to {result.target} "
            f"(mode={result.mode}, bridge={result.bridge_sha256}).",
            file=sys.stderr,
        )
        sys.exit(0)

    elif args.command == "hook":
        # Rewrite sys.argv so hook_main sees the event name at argv[1]
        sys.argv = ["copilot-command-ring", args.event_name]
        from .hook_main import main as hook_main

        hook_main()

    elif args.command == "refresh":
        from pathlib import Path

        from .setup_wizard import run_refresh

        venv_dir = Path(args.venv_dir) if args.venv_dir else None
        ok = run_refresh(venv_dir=venv_dir, package_spec=args.package_spec)
        sys.exit(0 if ok else 1)

    elif args.command in {"setup-status-ring", "wizard"}:
        from .setup_wizard import run_setup_status_ring_from_args

        ok = run_setup_status_ring_from_args(args)
        sys.exit(0 if ok else 1)

    elif args.command == "set-pixels":
        from pathlib import Path

        from .set_pixels import run_set_pixels

        config_dir = Path(args.config_dir) if args.config_dir else None
        ok = run_set_pixels(args.count, config_dir=config_dir)
        sys.exit(0 if ok else 1)

    elif args.command == "doctor":
        from pathlib import Path

        from .doctor import run_doctor

        config_dir = Path(args.config_dir) if args.config_dir else None
        exit_code = run_doctor(config_dir=config_dir, ping=not args.no_ping)
        sys.exit(exit_code)

    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
