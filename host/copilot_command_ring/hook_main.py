# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""CLI entry point for Copilot hook invocations.

Invoked as ``python -m copilot_command_ring.hook_main <event_name>``.
The Copilot CLI passes the hook payload as JSON on **stdin**.

For VS Code-compatible cross-tool configurations (``.claude/settings.json``)
that invoke the wrapper without an event-name argument, the event name is
recovered from the payload's ``hook_event_name`` field instead — every
documented VS Code-compatible payload includes this marker.

**stdout must remain empty** — Copilot interprets stdout as control JSON
for ``preToolUse`` / ``permissionRequest`` hooks.
"""

from __future__ import annotations

import json
import sys

from .config import load_config
from .events import normalize_event
from .logging_util import get_logger
from .protocol import format_message_for_log
from .sender import send_event


def main() -> None:
    """Read an event from argv/stdin, normalize it, and send to the device."""
    log = get_logger()

    try:
        raw = sys.stdin.read()
        try:
            payload: dict[str, object] = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, ValueError):
            payload = {}

        # Prefer the explicit argv form (how Copilot CLI invokes our deployed
        # wrapper). Fall back to ``hook_event_name`` in the payload body for
        # VS Code-compatible cross-tool configurations that route hooks to
        # this wrapper without a positional argument.
        event_name: str | None = None
        if len(sys.argv) >= 2 and sys.argv[1]:
            event_name = sys.argv[1]
        else:
            payload_event = payload.get("hook_event_name")
            if isinstance(payload_event, str) and payload_event:
                event_name = payload_event

        if not event_name:
            log.error(
                "Usage: python -m copilot_command_ring.hook_main <event_name> "
                "(or supply 'hook_event_name' in the stdin payload)"
            )
            sys.exit(1)

        config = load_config()
        message = normalize_event(event_name, payload)

        log.debug("Sending: %s", format_message_for_log(message))
        send_event(config, message)

    except SystemExit:
        raise
    except Exception:
        log.error("Unexpected error in hook_main", exc_info=True)

    sys.exit(0)


if __name__ == "__main__":
    main()
