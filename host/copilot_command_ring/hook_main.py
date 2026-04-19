# SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
# SPDX-License-Identifier: MIT
"""CLI entry point for Copilot hook invocations.

Invoked as ``python -m copilot_command_ring.hook_main <event_name>``.
The Copilot CLI passes the hook payload as JSON on **stdin**.

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
        if len(sys.argv) < 2:
            log.error("Usage: python -m copilot_command_ring.hook_main <event_name>")
            sys.exit(1)

        event_name: str = sys.argv[1]

        raw = sys.stdin.read()
        try:
            payload: dict[str, object] = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, ValueError):
            payload = {}

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
