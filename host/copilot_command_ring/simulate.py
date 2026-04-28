# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""Simulation tool — send test event sequences to the device."""

from __future__ import annotations

import argparse
import sys
import time

from .config import Config, load_config
from .events import normalize_event
from .logging_util import get_logger
from .protocol import serialize_message
from .sender import prepare_message, send_event

DEFAULT_SEQUENCE: list[tuple[str, dict[str, object]]] = [
    ("sessionStart", {"source": "new"}),
    ("userPromptSubmitted", {}),
    ("preToolUse", {"toolName": "edit"}),
    ("postToolUse", {"toolName": "edit", "toolResult": {"resultType": "success"}}),
    ("preToolUse", {"toolName": "grep"}),
    ("postToolUse", {"toolName": "grep", "toolResult": {"resultType": "denied"}}),
    ("preToolUse", {"toolName": "bash"}),
    ("postToolUseFailure", {"toolName": "bash", "error": "Command failed"}),
    ("permissionRequest", {"toolName": "bash"}),
    ("preToolUse", {"toolName": "ask_user"}),
    ("postToolUse", {"toolName": "ask_user", "toolResult": {"resultType": "success"}}),
    ("subagentStart", {"agentName": "reviewer"}),
    ("subagentStop", {"agentName": "reviewer"}),
    ("preCompact", {"trigger": "auto"}),
    (
        "errorOccurred",
        {
            "error": {"name": "ToolFailure", "message": "timeout"},
            "recoverable": True,
        },
    ),
    ("agentStop", {"stopReason": "end_turn"}),
    ("sessionEnd", {"reason": "user_exit"}),
]


def run_sequence(
    config: Config,
    sequence: list[tuple[str, dict[str, object]]],
    delay: float = 1.5,
) -> None:
    """Send each event in *sequence* to the device with a pause between them."""
    log = get_logger()
    total = len(sequence)

    for idx, (event_name, payload) in enumerate(sequence, start=1):
        message = normalize_event(event_name, payload)
        if config.dry_run:
            sys.stdout.write(
                serialize_message(prepare_message(config, message)).decode("utf-8"),
            )
        ok = send_event(config, message)
        status = "ok" if ok else "FAIL"
        print(
            f"[{idx}/{total}] {event_name} -> {status}",
            file=sys.stderr,
        )
        log.debug("Sent %s (payload=%s)", event_name, payload)

        if idx < total:
            time.sleep(delay)


def main() -> None:
    """CLI entry point for the simulation tool."""
    parser = argparse.ArgumentParser(
        description="Send a test event sequence to the Copilot Command Ring device.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to wait between events (default: 1.5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print JSON Lines without sending over serial",
    )
    args = parser.parse_args()

    config = load_config()
    if args.dry_run:
        config.dry_run = True

    print(
        f"Starting simulation ({len(DEFAULT_SEQUENCE)} events, "
        f"delay={args.delay}s, dry_run={config.dry_run})",
        file=sys.stderr,
    )

    run_sequence(config, DEFAULT_SEQUENCE, delay=args.delay)

    print("Simulation complete.", file=sys.stderr)


if __name__ == "__main__":
    main()
