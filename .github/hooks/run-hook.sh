#!/usr/bin/env bash
# Copilot Command Ring — hook wrapper for macOS/Linux
# Invoked by Copilot CLI hooks. Passes the event name and stdin payload to
# the Python host bridge. stdout MUST remain empty.

set -euo pipefail

EVENT_NAME="${1:?Usage: run-hook.sh <event_name>}"

# Resolve repo root relative to this script (.github/hooks/ -> repo root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOST_DIR="$REPO_ROOT/host"

# Set PYTHONPATH so copilot_command_ring is importable
export PYTHONPATH="$HOST_DIR${PYTHONPATH:+:$PYTHONPATH}"

# Find Python: prefer python3, fallback to python
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
fi

if [ -z "$PYTHON" ]; then
    # No Python found — fail silently, don't block Copilot
    exit 0
fi

# Pipe stdin through; stderr is forwarded, stdout stays clean
exec "$PYTHON" -m copilot_command_ring.hook_main "$EVENT_NAME" 2>&2

exit 0
