# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""CLI entry point for the ``copilot-command-ring`` console script.

Subcommands
-----------
setup                 Install global hooks (all repos, one-time).
deploy <target-dir>   Deploy hooks into a specific repository.
hook <event_name>     Handle a Copilot CLI hook event (called by deployed wrappers).
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    """Top-level CLI dispatcher."""
    parser = argparse.ArgumentParser(
        prog="copilot-command-ring",
        description="Copilot Command Ring — NeoPixel status ring for GitHub Copilot CLI",
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
        help="Overwrite existing hook files without prompting",
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

    args = parser.parse_args(argv)

    if args.command == "setup":
        from .deploy import setup_global_hooks

        ok = setup_global_hooks(force=args.force)
        sys.exit(0 if ok else 1)

    elif args.command == "deploy":
        from .deploy import deploy_hooks

        ok = deploy_hooks(args.target_dir, force=args.force)
        sys.exit(0 if ok else 1)

    elif args.command == "hook":
        # Rewrite sys.argv so hook_main sees the event name at argv[1]
        sys.argv = ["copilot-command-ring", args.event_name]
        from .hook_main import main as hook_main

        hook_main()

    elif args.command in {"setup-status-ring", "wizard"}:
        from .setup_wizard import run_setup_status_ring_from_args

        ok = run_setup_status_ring_from_args(args)
        sys.exit(0 if ok else 1)

    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
