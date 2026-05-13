#!/bin/bash
# ============================================================
# open-terminal.sh
#
# Double-click or run from shell to open an LXTerminal window
# for this repo.
#
# On first run, also installs .desktop shortcuts on the Desktop
# and in the application menu.
#
# Targets Raspberry Pi OS (Trixie / Debian 13) with LXTerminal.
#
# To use in another repo: copy this file to <repo>/scripts/.
# Optional local override: <repo>/.copilot-launcher.env with TAB_COLOR=#RRGGBB.
# ============================================================

# -----------------------------------------------------------
# Deploy-provided default tab color (hex).
# (Stored for deploy.py compatibility; used in .desktop Comment.)
# -----------------------------------------------------------
TAB_COLOR="#963885"

# -----------------------------------------------------------
# Derived values (from this script's filesystem location)
# -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_NAME="$(basename "$REPO_DIR")"

# -----------------------------------------------------------
# Repo-local override (optional; exact TAB_COLOR=#RRGGBB lines only)
# -----------------------------------------------------------
LAUNCHER_ENV="$REPO_DIR/.copilot-launcher.env"
if [ -f "$LAUNCHER_ENV" ]; then
    while IFS= read -r line; do
        if printf '%s\n' "$line" | grep -Eq '^TAB_COLOR=#[0-9A-Fa-f]{6}$'; then
            TAB_COLOR="${line#TAB_COLOR=}"
        fi
    done < "$LAUNCHER_ENV"
fi

# -----------------------------------------------------------
# Auto-install .desktop shortcuts on first run (idempotent)
# -----------------------------------------------------------
_install_desktop_entry() {
    local dest_dir="$1"
    local dest="$dest_dir/${REPO_NAME}.desktop"
    [ -f "$dest" ] && return
    mkdir -p "$dest_dir"
    cat > "$dest" << EOF
[Desktop Entry]
Type=Application
Name=$REPO_NAME
Comment=Open terminal in $REPO_NAME
Exec=lxterminal --working-directory="$REPO_DIR" --title="$REPO_NAME"
Icon=utilities-terminal
Terminal=false
Categories=Development;
EOF
    chmod +x "$dest"
    echo "Installed .desktop shortcut: $dest"
}

_install_desktop_entry "$HOME/Desktop"
_install_desktop_entry "$HOME/.local/share/applications"

# -----------------------------------------------------------
# Launch LXTerminal
# -----------------------------------------------------------
lxterminal --working-directory="$REPO_DIR" --title="$REPO_NAME" &
