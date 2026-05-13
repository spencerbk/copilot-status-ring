# Guided `/setup-status-ring` setup

The repo includes a Copilot CLI extension command named `/setup-status-ring`.
It guides a new user through the same setup path documented in the README while
keeping the durable setup logic in the Python package.

## What the wizard does

1. Creates or reuses `<repo>/.venv` inside your local clone (falls back to a
   user-level venv at `~/.local/share/copilot-command-ring/.venv` /
   `%LOCALAPPDATA%\copilot-command-ring\.venv` if no clone is detected).
2. Installs or upgrades `copilot-command-ring` into that environment from your
   local clone path (no network needed). Falls back to
   `git+https://github.com/spencerbk/copilot-status-ring.git` when no clone is
   detected.
3. Asks whether hooks should be installed globally for all repos or deployed to
   one target repo.
4. Prompts for the board, firmware runtime, NeoPixel data pin, and ring size
   (24 / 16 / 12 LEDs) using the current supported-board matrix.
5. Attempts host USB serial auto-detection when requested.
6. Requires explicit approval before preparing or writing firmware files.
7. Persists the chosen ring size to `~/.copilot-command-ring.local.json`
   (global scope) or `<repo>/.copilot-command-ring.local.json` (repo scope) by
   merging `pixel_count` into any existing config. Picking the default 24 with
   no existing config file leaves no file behind.
8. Runs a dry-run simulation command after hooks are installed.

CircuitPython can copy prepared `boot.py` and `code.py` to a detected or supplied
`CIRCUITPY` drive and attempts to install the `neopixel` dependency with
`circup`; if that library install fails, setup still completes and prints the
manual `CIRCUITPY/lib/neopixel.mpy` fallback. MicroPython uses `mpremote` after
approval. Arduino remains a guided/manual upload path unless you run the Arduino
tooling yourself.

## macOS/Linux bootstrap script

For a first setup on macOS or Linux, prefer the repo-level installer:

```bash
git clone https://github.com/spencerbk/copilot-status-ring.git
cd copilot-status-ring
./install.sh
```

`install.sh` is a thin bootstrap wrapper around this same Python wizard. It
creates `<repo>/.venv` inside the clone, installs the package into it from
local source, then runs `setup-status-ring` by module path so the user never
needs `copilot-command-ring` to already be on `PATH`.

## Fallback terminal command

If the slash command and `install.sh` are not available, run the Python wizard directly:

```powershell
copilot-command-ring setup-status-ring
```

For non-interactive callers, pass selections as JSON:

```powershell
@'
{
  "scope": "global",
  "board_id": "raspberry-pi-pico",
  "runtime": "circuitpython",
  "data_pin": "board.GP6",
  "pixel_count": 24,
  "auto_detect_port": true,
  "approve_firmware": false,
  "force_hooks": true
}
'@ | copilot-command-ring setup-status-ring --from-json - --yes
```

`pixel_count` is optional (defaults to `24`) and accepts `24`, `16`, or `12` —
the wizard merges your choice into the local JSON config as a side effect, so a
later run of the host bridge picks it up automatically.

Use `--options-json` to inspect the board/runtime matrix consumed by the
extension, `--plan-only` to print the commands that would run without
executing them, and `--venv-dir` / `--package-spec` to override the auto-detected
defaults (repo-local `.venv` and local-clone install spec).
