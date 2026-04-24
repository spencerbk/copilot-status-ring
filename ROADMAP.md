# Roadmap

## v1 — Core Implementation ✅

All v1 deliverables are complete.

| Area | Status | Details |
|------|--------|---------|
| **Host bridge** | ✅ Done | pip-installable Python package with CLI (`setup`, `deploy`, `hook`), event normalization, serial sender, auto-detection, config loading, dry-run mode |
| **Hook integration** | ✅ Done | Global hooks via `copilot-command-ring setup` (one-time, all repos) + per-repo `.github/hooks/` via `copilot-command-ring deploy` |
| **Serial protocol** | ✅ Done | Line-delimited JSON over USB serial with optional `session` field for multi-session arbitration |
| **CircuitPython firmware** | ✅ Done | State machine with 8 animation modes, multi-session tracking, board auto-detection, stale session pruning (CircuitPython 10.x) |
| **Arduino firmware** | ✅ Done | Full feature parity with CircuitPython: multi-session tracking (8 concurrent), TTL decay, stale pruning, priority arbitration, transient overlay, idle mode, startup animation, brightness boost, dual JSON parser, watchdog (RP2040), serial silence timeout, error recovery |
| **MicroPython firmware** | ✅ Done | Full feature-parity port: multi-session tracking, TTL decay, stale pruning, dedicated USB CDC data channel via micropython-lib. Auto-detection for RP2040/RP2350 boards wired to GPIO 6; manual `NEOPIXEL_PIN` override for other layouts and ESP32 variants. Degraded stdin fallback for ESP32-C3/C6. (MicroPython 1.24+) |
| **Host tests** | ✅ Done | Unit + integration coverage for event normalization, protocol, config, port detection, and deployment |
| **Documentation** | ✅ Done | Hardware wiring guide, OS setup docs (Windows/macOS/Linux), troubleshooting, hook event reference |
| **Cross-platform support** | ✅ Done | Windows (primary), macOS, Linux |

### v1 hook events

`sessionStart` · `sessionEnd` · `userPromptSubmitted` · `preToolUse` · `postToolUse` · `postToolUseFailure` · `permissionRequest` · `subagentStart` · `subagentStop` · `agentStop` · `preCompact` · `errorOccurred` · `notification`

### v1 animations

off · solid · flash · blink · pulse · spinner · wipe · chase · breathing

---

## v2 — Customization & Theming

User-facing personalization without changing code.

| Item | Description |
|------|-------------|
| Per-tool color themes | Different colors for different tool types (e.g., blue for `edit`, green for `bash`) |
| User-customizable themes via JSON config | Define color palettes and animation overrides in the local config file |

---

## v3 — Multi-Device & New Hardware

Extend beyond a single NeoPixel ring.

| Item | Description |
|------|-------------|
| Multiple LED devices | Drive more than one ring/strip from the same host bridge |
| Matrix or bar graph device | Support alternative LED layouts beyond the 24-pixel ring |
| Wireless transport | Communicate with the MCU over Wi-Fi or BLE instead of USB serial |

---

## v4 — Distribution & Packaging

Make installation easier for end users.

| Item | Status | Description |
|------|--------|-------------|
| pip install from Git | ✅ Done | `pip install git+https://github.com/spencerbk/copilot-status-ring.git` installs the host bridge and CLI |
| Global hooks CLI | ✅ Done | `copilot-command-ring setup` deploys hooks to `~/.copilot/hooks/` (one-time, all repos) |
| PyPI publishing | Planned | Publish to PyPI so users can `pip install copilot-command-ring` without the Git URL |
| Prebuilt standalone binaries | Planned | Single-file executables for Windows, macOS, and Linux (no Python install required) |

---

## Known Gaps / Future Hardening

Areas where the current implementation is intentionally pragmatic and may warrant follow-up work if real-world issues surface.

| Gap | Description |
|-----|-------------|
| Automated firmware regression tests | CircuitPython and MicroPython firmware logic (state machine, session tracker, stale-idle behavior) has no test harness in this repo. Changes are validated by static analysis (Ruff + Pyright) and manual hardware testing only. A host-side simulator or split-out pure-Python tracker module could enable pytest coverage without a real MCU. |
| Firmware-hang surfacing | Partially addressed. Firmware now includes a 10-minute serial-silence watchdog that triggers `supervisor.reload()` when active sessions exist but no host bytes arrive, recovering from wedged USB CDC channels (common on Windows selective suspend). The host also surfaces a one-shot stderr WARNING after 3 consecutive send failures. A true host→ring heartbeat with reconnect/resync still requires a persistent host daemon (see below). |
| USB disconnect/reconnect UX | When the ring is physically unplugged mid-session, the host logs a serial error and the hook exits silently. There is no visible host-side indicator that the ring has gone offline, and no automatic state resync when it returns. The 3-failures stderr WARNING is a minimal surface; a richer UX depends on a persistent host process. |
| Persistent host daemon with heartbeat | Deferred. A long-running host daemon could send periodic heartbeats, detect ring disconnection, and resync session state on reconnect. Currently blocked on zero-touch auto-start across Windows / macOS / Linux — the project's constraint is that no user action beyond the initial install is required. Revisit when platform-agnostic auto-start (launchd / systemd user units / Windows Task Scheduler) can be scripted as part of `install.ps1` / `install.sh`. |
| VS Code-compatible hook aliases | The host bridge currently targets Copilot CLI hook names and camelCase payloads. If VS Code agent-hook compatibility is added later, extend normalization to accept the alternate event aliases and payload shapes, then update tests and hook documentation together so CLI support remains the primary baseline. |

---

## Out of Scope

These items are explicitly out of scope for the foreseeable future:

- Audio output / sound effects
- Cloud logging or telemetry backend
- Bi-directional tool control via hooks
- Advanced permission-policy enforcement
- Background host daemon / long-running host process — multi-session arbitration is handled on-device, and the project prefers the one-shot hook model over a persistent process
- Desktop notification mirroring / system tray app — covered by the OS and Copilot CLI itself; out of scope for this hardware companion
- Host-side periodic heartbeat pings in the current one-shot hook model — not possible without a persistent host process. The firmware breathes indefinitely when all sessions are stale (`idle_mode: "breathing"`, the default) instead of going dark, so a heartbeat is unnecessary for the common case. A future persistent daemon could add one — see *Persistent host daemon with heartbeat* above.
