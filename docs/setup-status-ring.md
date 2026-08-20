# Guided `/setup-status-ring` setup

The repo includes a Copilot CLI extension command named `/setup-status-ring`.
It guides a new user through the same setup path documented in the README while
keeping the durable setup logic in the Python package.

## What the wizard does

1. Creates or reuses `<repo>/.venv` inside your local clone (falls back to a
   user-level venv at `~/.local/share/copilot-command-ring/.venv` /
   `%LOCALAPPDATA%\copilot-command-ring\.venv` if no clone is detected).
2. Installs or upgrades `copilot-command-ring` into that environment from your
   local clone path (no network needed). The wizard auto-detects local clones
   and installs them **editable** (`pip install -e .`), so `git pull` is enough
   to pick up host-side fixes — you do **not** need to re-run the wizard after
   updating. Falls back to a frozen install from
   `git+https://github.com/spencerbk/copilot-status-ring.git` when no clone is
   detected; users on that path should run `copilot-command-ring refresh` to
   pick up upstream changes (see
   [Recover from a stale install](troubleshooting.md#animations-look-wrong)).
3. Asks whether integration should be global (**Copilot CLI + local GitHub
   Copilot App**) or limited to one repository (**Copilot CLI hooks only**).
   Global setup installs native CLI hooks first, then deploys the marker-owned
   App extension in safe probe mode. Repository setup prints `GitHub Copilot
   App support requires global setup.` and never deploys the App extension.
4. Prompts for the board, firmware runtime, NeoPixel data pin, ring size
   (24 / 16 / 12 LEDs), and **idle mode** (**Breathing** keeps the ring lit
   with a dim breathing animation when every session is silent — the default;
   **Off** lets the ring go fully dark on `sessionEnd` or after a stale
   prune). Dismissing the ring-size prompt defaults to **24 LEDs** (the
   Adafruit NeoPixel Ring 24) instead of aborting setup; dismissing the
   idle-mode prompt defaults to **Breathing**.
5. Attempts host USB serial auto-detection when requested. After detection
   the wizard offers three options:
   - **Use `COMxx` (auto-detected)** — accept the detected port.
   - **Pick a different port** — choose from every enumerable serial device
     on the host.
   - **Skip — keep any existing saved port** — leave the previously saved
     `serial_port` (if any) untouched.

   When auto-detection finds nothing, the wizard still offers "Pick a port
   from the list" and "Skip". Firmware approval is asked as an independent
   prompt regardless of the port choice — CircuitPython firmware writes to
   the `CIRCUITPY` drive, which is independent of the host's data serial
   port.
6. Requires explicit approval before preparing or writing firmware files.
   When approved on a CircuitPython runtime, the wizard then offers three
   options for the install destination:
   - **Install to detected CIRCUITPY drive (`<path>`)** — copy `boot.py`
     and `code.py` directly to the auto-detected mounted drive.
   - **Enter a different drive path…** — type a mount path manually
     (e.g. `D:/` on Windows or `/Volumes/CIRCUITPY` on macOS). Dismissing
     the input or submitting empty is treated as a skip rather than a
     required-field error.
   - **Skip — prepare firmware files only, copy them manually later** —
     leave prepared files under the user-level setup directory; no drive
     is written to.

   When no CIRCUITPY drive is auto-detected the wizard drops the first
   option but still offers "Enter a drive path…" and "Skip". The chosen
   ring size is templated into the copied source — `NUM_PIXELS` for
   CircuitPython/MicroPython and `#define PIXEL_COUNT` in the Arduino
   `copilot_types.h` header — so the firmware boots with the correct LED
   count even before the host bridge has sent its first message.
7. Persists the chosen ring size, idle mode, and serial port to
   `~/.copilot-command-ring.local.json` (global scope) or
   `<repo>/.copilot-command-ring.local.json` (repo scope) by merging
   `pixel_count`, `idle_mode` (when you've made a non-default selection or
   the file already contains one), and `serial_port` (if you picked one)
   into any existing config. Picking the default 24 with the default
   breathing idle mode, no chosen port, and no existing file leaves no
   file behind. **Precedence:** at hook time the host walks parents of
   the working directory first and uses any per-repo file it finds; only
   when no per-repo file exists does it fall back to the global
   `~/.copilot-command-ring.local.json`. A stale per-repo file will
   silently shadow the wizard's globally-saved choice — the wizard
   prints a `Warning: ... shadows the global save` line when it detects
   this case (see
   ["Ring goes dark unexpectedly during active sessions"](troubleshooting.md#ring-goes-dark-unexpectedly-during-active-sessions)
   and
   ["The host keeps sending the wrong pixel_count"](troubleshooting.md#animations-look-wrong)
   for recovery).
8. Runs a dry-run simulation command after hooks are installed.

## Local GitHub Copilot App extension

Global setup manages this exact layout:

```text
$COPILOT_HOME/extensions/copilot-app-status-ring/
├── extension.mjs
├── .copilot-command-ring-managed.json
└── releases/<bridge-sha256>/bridge.mjs
```

Without `COPILOT_HOME`, the root is `~/.copilot`. Deployment uses a
cross-platform exclusive lock, same-filesystem staging, a content-addressed
bridge release, and atomic marker replacement. An update refuses a missing or
invalid ownership marker even with `--force`; unknown files are never silently
deleted. The marker is the active-release pointer and records schema version
`1`, owner `copilot-command-ring`, extension `copilot-app-status-ring`, the
active SHA, tracked releases, and mode (`probe` or `forwarding`).

App discovery, `joinSession`, host context, and event subscriptions are
experimental runtime-backed interfaces rather than documented stable SDK
promises. Setup therefore deploys `probe` mode first. With
`COPILOT_RING_APP_DEBUG=1`, open the standalone App from a different repository
that has no local hooks/extensions and require:

```text
[copilot-command-ring] app-extension discovered platform=desktop active=true mode=probe
```

Also verify Copilot CLI remains non-desktop/inactive and its native hooks still
send once. Then explicitly attest that proof:

```powershell
copilot-command-ring deploy-app-extension --activate-forwarding
```

If discovery requires restarting the App, do not infer success; leave probe
mode in place until the manual proof can be performed. The direct recovery
command `copilot-command-ring deploy-app-extension` refreshes packaged files
without activating an unproven probe.

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

`copilot-command-ring refresh` first reinstalls Python, then invokes the newly
installed `copilot-command-ring deploy-app-extension` executable. It does not
reuse stale in-process deployment code.

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
  "idle_mode": "breathing",
  "serial_port": "COM12",
  "auto_detect_port": true,
  "approve_firmware": false,
  "force_hooks": true
}
'@ | copilot-command-ring setup-status-ring --from-json - --yes
```

`pixel_count` is optional (defaults to `24`) and accepts `24`, `16`, or `12` —
the wizard merges your choice into the local JSON config as a side effect, so a
later run of the host bridge picks it up automatically.

`idle_mode` is optional (defaults to `"breathing"`) and accepts `"breathing"`
or `"off"`. Omitting it, leaving it empty, or passing `null` keeps the default;
any other string is rejected as a setup error. The chosen value is persisted
into the local JSON config when it is non-default or the file already contains
an `idle_mode` entry.

`serial_port` is optional. When set (e.g. `"COM12"`, `"/dev/ttyACM0"`), it is
persisted into the same local JSON config so the host bridge uses it directly.
When omitted or `null`, the wizard preserves any pre-existing `serial_port`
entry instead of overwriting it.

Use `--options-json` to inspect the board/runtime matrix consumed by the
extension, `--list-ports-json` to enumerate every host serial port (the
extension calls this for the manual port picker), `--plan-only` to print the
commands that would run without executing them, and `--venv-dir` /
`--package-spec` to override the auto-detected defaults (repo-local `.venv`
and local-clone install spec).
