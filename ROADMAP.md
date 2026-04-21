# Roadmap

## v1 — Core Implementation ✅

All v1 deliverables are complete.

| Area | Status | Details |
|------|--------|---------|
| **Host bridge** | ✅ Done | pip-installable Python package with CLI (`setup`, `deploy`, `hook`), event normalization, serial sender, auto-detection, config loading, dry-run mode |
| **Hook integration** | ✅ Done | Global hooks via `copilot-command-ring setup` (one-time, all repos) + per-repo `.github/hooks/` via `copilot-command-ring deploy` |
| **Serial protocol** | ✅ Done | Line-delimited JSON over USB serial with optional `session` field for multi-session arbitration |
| **CircuitPython firmware** | ✅ Done | State machine with 8 animation modes, multi-session tracking, board auto-detection, stale session pruning (CircuitPython 10.x) |
| **Arduino firmware** | ✅ Done | Semantically equivalent animations using Adafruit_NeoPixel (single-session mode) |
| **Host tests** | ✅ Done | Unit + integration coverage for event normalization, protocol, config, port detection, and deployment |
| **Documentation** | ✅ Done | Hardware wiring guide, OS setup docs (Windows/macOS/Linux), troubleshooting, hook event reference |
| **Cross-platform support** | ✅ Done | Windows (primary), macOS, Linux |

### v1 hook events

`sessionStart` · `sessionEnd` · `userPromptSubmitted` · `preToolUse` · `postToolUse` · `postToolUseFailure` · `permissionRequest` · `subagentStart` · `subagentStop` · `agentStop` · `preCompact` · `errorOccurred` · `notification`

### v1 animations

off · solid · flash · blink · spinner · wipe · chase · breathing

---

## v2 — Customization & Theming

User-facing personalization without changing code.

| Item | Description |
|------|-------------|
| Per-tool color themes | Different colors for different tool types (e.g., blue for `edit`, green for `bash`) |
| User-customizable themes via JSON config | Define color palettes and animation overrides in the local config file |

---

## v3 — Background Daemon & Desktop Integration

Replace direct hook-to-serial calls with a persistent host process.

> **Note:** Multi-session state arbitration was delivered without a daemon — the firmware
> now tracks sessions and resolves priorities on-device. A daemon would still provide
> benefits for connection persistence and desktop integration.

| Item | Description |
|------|-------------|
| Background host daemon | Long-running process that holds the serial connection open; hooks send messages to the daemon instead of opening/closing serial per event |
| Desktop notification mirroring | Mirror Copilot CLI state to OS-native desktop notifications |
| Desktop tray app | System tray presence for status and configuration |

---

## v4 — Multi-Device & New Hardware

Extend beyond a single NeoPixel ring.

| Item | Description |
|------|-------------|
| Multiple LED devices | Drive more than one ring/strip from the same host bridge |
| Matrix or bar graph device | Support alternative LED layouts beyond the 24-pixel ring |
| Wireless transport | Communicate with the MCU over Wi-Fi or BLE instead of USB serial |

---

## v5 — Distribution & Packaging

Make installation easier for end users.

| Item | Status | Description |
|------|--------|-------------|
| pip install from Git | ✅ Done | `pip install git+https://github.com/spencerbk/copilot-status-ring.git` installs the host bridge and CLI |
| Global hooks CLI | ✅ Done | `copilot-command-ring setup` deploys hooks to `~/.copilot/hooks/` (one-time, all repos) |
| PyPI publishing | Planned | Publish to PyPI so users can `pip install copilot-command-ring` without the Git URL |
| Prebuilt standalone binaries | Planned | Single-file executables for Windows, macOS, and Linux (no Python install required) |

---

## Out of Scope

These items are explicitly out of scope for the foreseeable future:

- Audio output / sound effects
- Cloud logging or telemetry backend
- Bi-directional tool control via hooks
- Advanced permission-policy enforcement
