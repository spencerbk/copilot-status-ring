#!/usr/bin/env bash
# Copilot Command Ring — cross-platform validation (macOS / Linux)
# Checks that the host environment is correctly configured.
#
# Usage: bash scripts/validate-platform.sh
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOST_DIR="$REPO_ROOT/host"

PASS=0
FAIL=0
WARN=0

pass() { PASS=$((PASS + 1)); printf "  ✅ %s\n" "$1"; }
fail() { FAIL=$((FAIL + 1)); printf "  ❌ %s\n" "$1"; }
warn() { WARN=$((WARN + 1)); printf "  ⚠️  %s\n" "$1"; }
section() { printf "\n── %s ──\n" "$1"; }

# --------------------------------------------------------------------------
section "Python"

PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
fi

if [ -n "$PYTHON" ]; then
    PY_VER=$($PYTHON --version 2>&1)
    pass "Python found: $PYTHON ($PY_VER)"
else
    fail "Python 3 not found (tried python3, python)"
fi

# --------------------------------------------------------------------------
section "Dependencies"

if [ -n "$PYTHON" ]; then
    if $PYTHON -c "import serial" 2>/dev/null; then
        SERIAL_VER=$($PYTHON -c "import serial; print(serial.VERSION)" 2>/dev/null || echo "unknown")
        pass "pyserial importable (version $SERIAL_VER)"
    else
        fail "pyserial not installed — run: pip3 install pyserial"
    fi
else
    fail "Skipped (no Python)"
fi

# --------------------------------------------------------------------------
section "Hook wrapper"

HOOK_SCRIPT="$REPO_ROOT/.github/hooks/run-hook.sh"
if [ -f "$HOOK_SCRIPT" ]; then
    pass "run-hook.sh exists"
else
    fail "run-hook.sh not found at $HOOK_SCRIPT"
fi

if [ -f "$HOOK_SCRIPT" ]; then
    # Verify it can be parsed without syntax errors
    if bash -n "$HOOK_SCRIPT" 2>/dev/null; then
        pass "run-hook.sh has valid syntax"
    else
        fail "run-hook.sh has syntax errors"
    fi
fi

HOOK_JSON="$REPO_ROOT/.github/hooks/copilot-command-ring.json"
if [ -f "$HOOK_JSON" ]; then
    pass "copilot-command-ring.json exists"
    if [ -n "$PYTHON" ]; then
        if $PYTHON -c "import json, sys; json.load(open(sys.argv[1]))" "$HOOK_JSON" 2>/dev/null; then
            pass "copilot-command-ring.json is valid JSON"
        else
            fail "copilot-command-ring.json is not valid JSON"
        fi
    else
        warn "Skipping JSON validation (no Python interpreter)"
    fi
else
    fail "copilot-command-ring.json not found"
fi

# --------------------------------------------------------------------------
section "Host bridge dry-run"

if [ -n "$PYTHON" ]; then
    export PYTHONPATH="$HOST_DIR${PYTHONPATH:+:$PYTHONPATH}"
    export COPILOT_RING_DRY_RUN=1

    EVENTS=(
        sessionStart sessionEnd userPromptSubmitted
        preToolUse postToolUse postToolUseFailure
        permissionRequest subagentStart subagentStop
        agentStop preCompact errorOccurred notification
    )

    ALL_EVENTS_OK=true
    for EVT in "${EVENTS[@]}"; do
        if printf '{}\n' | $PYTHON -m copilot_command_ring.hook_main "$EVT" >/dev/null 2>&1; then
            :
        else
            EXIT_CODE=$?
            fail "hook_main $EVT exited with code $EXIT_CODE"
            ALL_EVENTS_OK=false
        fi
    done
    if [ "$ALL_EVENTS_OK" = true ]; then
        pass "All ${#EVENTS[@]} events exit cleanly in dry-run mode"
    fi

    # Verify stdout stays empty for preToolUse (critical for Copilot CLI)
    STDOUT_CHECK=$(echo '{"toolName":"bash"}' | $PYTHON -m copilot_command_ring.hook_main preToolUse 2>/dev/null)
    if [ -z "$STDOUT_CHECK" ]; then
        pass "preToolUse produces no stdout output"
    else
        fail "preToolUse wrote to stdout (would interfere with Copilot CLI)"
    fi
fi

# --------------------------------------------------------------------------
section "Serial port detection"

if [ -n "$PYTHON" ]; then
    if $PYTHON -c "
from copilot_command_ring.detect_ports import detect_port
result = detect_port()
if result:
    print(result)
else:
    print('(none detected)')
" 2>/dev/null; then
        pass "Port detection runs without error"
    else
        warn "Port detection raised an error (may be normal if pyserial is not fully installed)"
    fi
fi

# --------------------------------------------------------------------------
section "Tests"

if [ -n "$PYTHON" ]; then
    if $PYTHON -m pytest --version &>/dev/null; then
        pass "pytest is available"
        if $PYTHON -m pytest "$REPO_ROOT/tests/" -q --tb=line 2>&1 | tail -1 | grep -q "passed"; then
            TEST_SUMMARY=$($PYTHON -m pytest "$REPO_ROOT/tests/" -q --tb=line 2>&1 | tail -1)
            pass "Tests: $TEST_SUMMARY"
        else
            TEST_SUMMARY=$($PYTHON -m pytest "$REPO_ROOT/tests/" -q --tb=line 2>&1 | tail -1)
            fail "Tests: $TEST_SUMMARY"
        fi
    else
        warn "pytest not installed — skipping test run"
    fi
fi

# --------------------------------------------------------------------------
section "Firmware files"

for F in boot.py code.py; do
    if [ -f "$REPO_ROOT/firmware/circuitpython/$F" ]; then
        pass "firmware/circuitpython/$F exists"
    else
        fail "firmware/circuitpython/$F missing"
    fi
done

if [ -f "$REPO_ROOT/firmware/arduino/copilot_command_ring/copilot_command_ring.ino" ]; then
    pass "firmware/arduino/copilot_command_ring.ino exists"
else
    fail "firmware/arduino/copilot_command_ring.ino missing"
fi

# --------------------------------------------------------------------------
printf "\n── Summary ──\n"
printf "  Passed: %d  |  Failed: %d  |  Warnings: %d\n\n" "$PASS" "$FAIL" "$WARN"

if [ "$FAIL" -gt 0 ]; then
    echo "Some checks failed. See above for details."
    exit 1
else
    echo "All checks passed! Your environment is ready."
    exit 0
fi
