#!/usr/bin/env bash
# Bootstrap the Copilot Command Ring setup on macOS/Linux.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$SCRIPT_DIR"
STATE_BASE="${XDG_DATA_HOME:-$HOME/.local/share}"
STATE_DIR="$STATE_BASE/copilot-command-ring"
LOG_FILE="$STATE_DIR/install.log"

YES=0
DRY_RUN=0
SCOPE="global"
REPO_PATH=""
BOARD_ID="raspberry-pi-pico"
RUNTIME="circuitpython"
PIN=""
PIN_SET=0
AUTO_DETECT_PORT="true"
PREPARE_FIRMWARE="auto"
FIRMWARE_TARGET=""
VENV_DIR="$REPO_ROOT/.venv"
PACKAGE_SPEC="."

usage() {
    cat <<'EOF'
Usage: ./install.sh [options]

Bootstrap Copilot Command Ring on macOS/Linux without requiring
copilot-command-ring to already be on PATH.

Defaults:
  --global --board raspberry-pi-pico --runtime circuitpython --pin board.GP6

Options:
  --yes                    Accept safe defaults without prompting.
  --dry-run                Print the setup plan; do not create a venv or install.
  --global                 Install global Copilot CLI hooks (default).
  --repo PATH              Deploy hooks to one repository instead of globally.
  --board ID               Board id or alias (default: raspberry-pi-pico).
  --runtime ID             Firmware runtime (default: circuitpython).
  --pin PIN                NeoPixel data pin override.
  --no-detect-port         Skip host USB serial auto-detection.
  --prepare-firmware       Prepare firmware files; MicroPython runs mpremote.
  --no-firmware            Do not prepare or write firmware files.
  --firmware-target PATH   Copy CircuitPython files to a CIRCUITPY drive.
  --venv-dir PATH          Dedicated setup virtual environment path
                           (default: <repo>/.venv inside the clone).
  --package-spec SPEC      pip package spec to install (default: local repo).
  -h, --help               Show this help.

Examples:
  ./install.sh
  ./install.sh --yes
  ./install.sh --firmware-target /media/$USER/CIRCUITPY
  ./install.sh --repo ~/code/my-project
EOF
}

info() {
    printf "==> %s\n" "$*"
}

warn() {
    printf "WARNING: %s\n" "$*" >&2
}

die() {
    printf "ERROR: %s\n" "$*" >&2
    printf "Log: %s\n" "$LOG_FILE" >&2
    exit 1
}

on_error() {
    local status=$?
    local line=$1
    local command=$2
    printf "\nERROR: install failed during: %s\n" "$PHASE" >&2
    printf "Command: %s\n" "$command" >&2
    printf "Line: %s\n" "$line" >&2
    printf "Log: %s\n" "$LOG_FILE" >&2
    exit "$status"
}

require_arg() {
    local option=$1
    local value=${2-}
    if [[ -z "$value" || "$value" == --* ]]; then
        die "$option requires a value"
    fi
}

confirm() {
    local prompt=$1
    local default=${2:-no}
    local suffix="[y/N]"
    if [[ "$default" == "yes" ]]; then
        suffix="[Y/n]"
    fi

    local answer
    read -r -p "$prompt $suffix " answer
    answer="$(printf "%s" "$answer" | tr '[:upper:]' '[:lower:]')"
    if [[ -z "$answer" ]]; then
        [[ "$default" == "yes" ]]
        return
    fi
    [[ "$answer" == "y" || "$answer" == "yes" ]]
}

python_supports_version() {
    "$1" - <<'PY'
import sys

raise SystemExit(0 if sys.version_info >= (3, 9) else 1)
PY
}

find_python() {
    local candidate path
    for candidate in python3 python; do
        path=$(command -v "$candidate" 2>/dev/null || true)
        if [[ -n "$path" ]] && python_supports_version "$path"; then
            printf "%s\n" "$path"
            return 0
        fi
    done
    return 1
}

detect_circuitpy_mount() {
    local candidate
    local candidates=("/Volumes/CIRCUITPY")
    if [[ -n "${USER:-}" ]]; then
        candidates+=("/media/$USER/CIRCUITPY" "/run/media/$USER/CIRCUITPY")
    fi

    for candidate in "${candidates[@]}"; do
        if [[ -d "$candidate" ]]; then
            printf "%s\n" "$candidate"
            return 0
        fi
    done
    return 1
}

resolve_default_pin() {
    PYTHONPATH="$REPO_ROOT/host" "$BASE_PYTHON" - "$BOARD_ID" "$RUNTIME" <<'PY'
import sys

from copilot_command_ring.boards import get_runtime

runtime = get_runtime(sys.argv[1], sys.argv[2])
print(runtime.default_pin or "")
PY
}

build_payload() {
    "$BASE_PYTHON" - \
        "$SCOPE" \
        "$BOARD_ID" \
        "$RUNTIME" \
        "$PIN" \
        "$REPO_PATH" \
        "$AUTO_DETECT_PORT" \
        "$APPROVE_FIRMWARE" \
        "$FIRMWARE_TARGET" <<'PY'
import json
import sys

scope, board_id, runtime, pin, repo_path, auto_detect, approve, target = sys.argv[1:]

payload = {
    "scope": scope,
    "board_id": board_id,
    "runtime": runtime,
    "data_pin": pin or None,
    "repo_path": repo_path or None,
    "auto_detect_port": auto_detect == "true",
    "approve_firmware": approve == "true",
    "firmware_target": target or None,
    "force_hooks": True,
}
print(json.dumps(payload))
PY
}

run() {
    local command=("$@")
    printf "+ %q" "${command[0]}"
    shift
    local arg
    for arg in "$@"; do
        printf " %q" "$arg"
    done
    printf "\n"
    "${command[@]}"
}

print_summary() {
    printf "\nCopilot Command Ring setup plan\n"
    printf "  Scope: %s\n" "$SCOPE"
    if [[ "$SCOPE" == "repo" ]]; then
        printf "  Repository: %s\n" "$REPO_PATH"
    fi
    printf "  Board: %s\n" "$BOARD_ID"
    printf "  Runtime: %s\n" "$RUNTIME"
    printf "  Data pin: %s\n" "${PIN:-auto}"
    printf "  Venv: %s\n" "$VENV_DIR"
    printf "  Package: %s\n" "$PACKAGE_SPEC"
    if [[ -n "$FIRMWARE_TARGET" ]]; then
        printf "  Firmware target: %s\n" "$FIRMWARE_TARGET"
    elif [[ "$APPROVE_FIRMWARE" == "true" ]]; then
        printf "  Firmware: prepare files in user state directory\n"
    else
        printf "  Firmware: skipped\n"
    fi
    printf "\n"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --yes)
            YES=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --global)
            SCOPE="global"
            REPO_PATH=""
            shift
            ;;
        --repo)
            require_arg "$1" "${2-}"
            SCOPE="repo"
            REPO_PATH="$2"
            shift 2
            ;;
        --board)
            require_arg "$1" "${2-}"
            BOARD_ID="$2"
            shift 2
            ;;
        --runtime)
            require_arg "$1" "${2-}"
            RUNTIME="$2"
            shift 2
            ;;
        --pin)
            require_arg "$1" "${2-}"
            PIN="$2"
            PIN_SET=1
            shift 2
            ;;
        --no-detect-port)
            AUTO_DETECT_PORT="false"
            shift
            ;;
        --prepare-firmware)
            PREPARE_FIRMWARE="true"
            shift
            ;;
        --no-firmware)
            PREPARE_FIRMWARE="false"
            shift
            ;;
        --firmware-target)
            require_arg "$1" "${2-}"
            FIRMWARE_TARGET="$2"
            shift 2
            ;;
        --venv-dir)
            require_arg "$1" "${2-}"
            VENV_DIR="$2"
            shift 2
            ;;
        --package-spec)
            require_arg "$1" "${2-}"
            PACKAGE_SPEC="$2"
            shift 2
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

mkdir -p "$STATE_DIR"
: > "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

PHASE="startup"
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

PHASE="detect Python"
if ! BASE_PYTHON="$(find_python)"; then
    die "Python 3.9+ is required. Install Python, then rerun ./install.sh."
fi
info "Using $("$BASE_PYTHON" --version 2>&1) at $BASE_PYTHON"

PHASE="check repository"
cd "$REPO_ROOT"
[[ -f "$REPO_ROOT/host/copilot_command_ring/cli.py" ]] || \
    die "Run this script from a full copilot-status-ring clone."
[[ -f "$REPO_ROOT/firmware/circuitpython/boot.py" ]] || \
    die "Missing CircuitPython firmware files; run from a full repository clone."
[[ -f "$REPO_ROOT/firmware/circuitpython/code.py" ]] || \
    die "Missing CircuitPython firmware files; run from a full repository clone."

if [[ "$SCOPE" == "repo" && ! -d "$REPO_PATH" ]]; then
    die "Repository path is not a directory: $REPO_PATH"
fi

if [[ "$PREPARE_FIRMWARE" == "false" && -n "$FIRMWARE_TARGET" ]]; then
    die "--firmware-target cannot be combined with --no-firmware"
fi

RUNTIME="$(printf "%s" "$RUNTIME" | tr '[:upper:]' '[:lower:]')"

PHASE="resolve board defaults"
if [[ "$PIN_SET" -eq 0 ]]; then
    PIN="$(resolve_default_pin)"
fi

APPROVE_FIRMWARE="false"
if [[ "$PREPARE_FIRMWARE" == "true" ]]; then
    APPROVE_FIRMWARE="true"
elif [[ "$PREPARE_FIRMWARE" == "auto" && "$RUNTIME" == "circuitpython" ]]; then
    APPROVE_FIRMWARE="true"
fi
if [[ -n "$FIRMWARE_TARGET" ]]; then
    APPROVE_FIRMWARE="true"
fi

if [[ "$RUNTIME" == "circuitpython" && -z "$FIRMWARE_TARGET" && "$PREPARE_FIRMWARE" != "false" ]]; then
    detected_circuitpy="$(detect_circuitpy_mount || true)"
    if [[ -n "$detected_circuitpy" ]]; then
        if [[ "$YES" -eq 0 ]]; then
            if confirm "Detected CIRCUITPY at $detected_circuitpy. Copy firmware there now?" "no"; then
                FIRMWARE_TARGET="$detected_circuitpy"
                APPROVE_FIRMWARE="true"
            fi
        else
            info "Detected CIRCUITPY at $detected_circuitpy; not writing without --firmware-target."
        fi
    fi
fi

if [[ "$(uname -s)" == "Linux" ]]; then
    groups_text="$(id -nG 2>/dev/null || true)"
    case " $groups_text " in
        *" dialout "*|*" uucp "*) ;;
        *)
            warn "Your user is not in dialout/uucp. If serial sends fail, run:"
            warn "  sudo usermod -aG dialout \$USER"
            warn "Then log out and back in."
            ;;
    esac
fi

if command -v copilot >/dev/null 2>&1; then
    if ! copilot --version >/dev/null 2>&1; then
        warn "GitHub Copilot CLI was found but did not report a version."
    fi
else
    warn "GitHub Copilot CLI was not found on PATH; install it before expecting hooks to fire."
fi

if [[ "$RUNTIME" == "micropython" && "$PREPARE_FIRMWARE" == "true" && "$YES" -eq 0 ]]; then
    confirm "MicroPython firmware setup will run mpremote against the connected board. Continue?" "no" || \
        die "MicroPython firmware setup was not approved."
fi

payload="$(build_payload)"

if [[ "$DRY_RUN" -eq 1 ]]; then
    PHASE="build dry-run setup plan"
    print_summary
    printf "%s\n" "$payload" | PYTHONPATH="$REPO_ROOT/host" \
        "$BASE_PYTHON" -m copilot_command_ring.cli setup-status-ring \
        --from-json - \
        --plan-only \
        --venv-dir "$VENV_DIR" \
        --package-spec "$PACKAGE_SPEC"
    info "Dry run complete. No setup changes were made."
    exit 0
fi

print_summary
if [[ "$YES" -eq 0 ]]; then
    confirm "Proceed with setup?" "yes" || die "Aborted."
fi

PHASE="create virtual environment"
mkdir -p "$(dirname "$VENV_DIR")"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    if ! "$BASE_PYTHON" -m venv "$VENV_DIR"; then
        die "Could not create the virtual environment. On Debian/Ubuntu, install python3-venv."
    fi
fi
VENV_PYTHON="$VENV_DIR/bin/python"
[[ -x "$VENV_PYTHON" ]] || die "Virtual environment Python was not created: $VENV_PYTHON"

PHASE="upgrade pip"
run "$VENV_PYTHON" -m pip install --upgrade pip

PHASE="install package"
run "$VENV_PYTHON" -m pip install --upgrade "$PACKAGE_SPEC"

PHASE="verify package"
"$VENV_PYTHON" -m copilot_command_ring.cli --help >/dev/null

PHASE="run setup wizard"
printf "%s\n" "$payload" | "$VENV_PYTHON" -m copilot_command_ring.cli setup-status-ring \
    --from-json - \
    --yes \
    --venv-dir "$VENV_DIR" \
    --package-spec "$PACKAGE_SPEC" \
    --skip-install

if [[ "$RUNTIME" == "circuitpython" && -z "$FIRMWARE_TARGET" && "$APPROVE_FIRMWARE" == "true" ]]; then
    firmware_dir="$STATE_DIR/firmware/circuitpython"
    info "Firmware files were prepared in: $firmware_dir"
    info "After flashing CircuitPython, copy boot.py and code.py to CIRCUITPY."
    info "If neopixel was not installed automatically, copy neopixel.mpy to CIRCUITPY/lib/."
fi

info "Setup complete."
info "Log: $LOG_FILE"
