#!/usr/bin/env bash
# Copilot Command Ring — simulate hook events (macOS/Linux)
# Sends a test sequence through the host bridge for firmware validation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="$REPO_ROOT/host${PYTHONPATH:+:$PYTHONPATH}"

PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "Error: Python not found" >&2
    exit 1
fi

echo "Running Copilot Command Ring simulation..."
exec "$PYTHON" -m copilot_command_ring.simulate --dry-run "$@"
