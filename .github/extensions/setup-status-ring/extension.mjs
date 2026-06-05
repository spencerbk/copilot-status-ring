// SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
// SPDX-License-Identifier: MIT

import { execFile } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { joinSession } from "@github/copilot-sdk/extension";

const extensionDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(extensionDir, "..", "..", "..");
const hostDir = path.join(repoRoot, "host");
const venvDir = path.join(repoRoot, ".venv");
const pythonCandidates =
    process.platform === "win32"
        ? [
              { executable: "python", prefixArgs: [] },
              { executable: "py", prefixArgs: ["-3"] },
          ]
        : [
              { executable: "python3", prefixArgs: [] },
              { executable: "python", prefixArgs: [] },
          ];

function pythonEnv() {
    return {
        ...process.env,
        PYTHONPATH: process.env.PYTHONPATH
            ? `${hostDir}${path.delimiter}${process.env.PYTHONPATH}`
            : hostDir,
    };
}

function runPythonCandidate(candidate, args, input, { allowNonZero = false } = {}) {
    return new Promise((resolve, reject) => {
        const child = execFile(
            candidate.executable,
            [...candidate.prefixArgs, "-m", "copilot_command_ring.cli", ...args],
            {
                cwd: repoRoot,
                env: pythonEnv(),
                maxBuffer: 1024 * 1024,
                timeout: 10 * 60 * 1000,
            },
            (error, stdout, stderr) => {
                if (error) {
                    if (allowNonZero && error.code !== "ENOENT") {
                        // Doctor and other diagnostic commands intentionally exit
                        // non-zero when checks fail. Their stdout *is* the report
                        // we want to surface, so preserve it instead of throwing
                        // away with only the stderr line.
                        resolve({ stdout, stderr, code: error.code ?? 1 });
                        return;
                    }
                    const wrapped = new Error(stderr || error.message);
                    wrapped.code = error.code;
                    reject(wrapped);
                    return;
                }
                resolve({ stdout, stderr, code: 0 });
            },
        );
        if (input !== undefined) {
            child.stdin.end(input);
        }
    });
}

async function runPython(args, input, options) {
    let lastError;
    for (const candidate of pythonCandidates) {
        try {
            return await runPythonCandidate(candidate, args, input, options);
        } catch (error) {
            lastError = error;
            if (error.code !== "ENOENT") {
                throw error;
            }
        }
    }
    throw lastError || new Error("No Python interpreter found.");
}

async function loadOptions() {
    const { stdout } = await runPython(["setup-status-ring", "--options-json"]);
    return JSON.parse(stdout);
}

async function detectPort(session) {
    try {
        const { stdout } = await runPython(["setup-status-ring", "--detect-port-json"]);
        return JSON.parse(stdout);
    } catch (error) {
        await session.log(`Serial auto-detection failed: ${error.message}`, { level: "warning" });
        return { detected: false, port: null };
    }
}

async function detectCircuitPy(session) {
    try {
        const { stdout } = await runPython(["setup-status-ring", "--detect-circuitpy-json"]);
        return JSON.parse(stdout);
    } catch (error) {
        await session.log(`CIRCUITPY drive detection failed: ${error.message}`, { level: "warning" });
        return { detected: false, path: null };
    }
}

async function loadPorts(session) {
    try {
        const { stdout } = await runPython(["setup-status-ring", "--list-ports-json"]);
        const parsed = JSON.parse(stdout);
        return Array.isArray(parsed.ports) ? parsed.ports : [];
    } catch (error) {
        await session.log(`Serial port enumeration failed: ${error.message}`, {
            level: "warning",
        });
        return [];
    }
}

async function pickSerialPort(session, autoDetected) {
    // 3-option flow when auto-detect found a match, 2-option flow otherwise.
    // Always offers "Skip" so the user can leave any pre-existing saved port
    // untouched. Returns the chosen device string (e.g. "COM12") or null
    // when the user skipped.
    const USE_DETECTED = "use_detected";
    const PICK_DIFFERENT = "pick_different";
    const PICK_FROM_LIST = "pick_from_list";
    const SKIP = "skip";

    const options = [];
    if (autoDetected) {
        options.push({ label: `Use ${autoDetected} (auto-detected)`, value: USE_DETECTED });
        options.push({ label: "Pick a different port", value: PICK_DIFFERENT });
    } else {
        options.push({ label: "Pick a port from the list", value: PICK_FROM_LIST });
    }
    options.push({ label: "Skip — keep any existing saved port", value: SKIP });

    const decisionLabel = await session.ui.select(
        "How should the ring's serial port be configured?",
        options.map((option) => option.label),
    );
    if (!decisionLabel) {
        // Dismiss => skip (do not abort the wizard).
        await session.log("Port selection skipped; keeping any existing saved port.");
        return null;
    }
    const decision = optionByLabel(options, decisionLabel);
    if (decision === USE_DETECTED) return autoDetected;
    if (decision === SKIP) return null;

    const ports = await loadPorts(session);
    if (ports.length === 0) {
        await session.log(
            "No serial ports could be enumerated. Skipping port selection.",
            { level: "warning" },
        );
        return null;
    }
    const portItems = ports.map((entry) => ({
        label: entry.description
            ? `${entry.device} — ${entry.description}`
            : entry.device,
        value: entry.device,
    }));
    const portLabel = await session.ui.select(
        "Which serial port should the ring use?",
        portItems.map((item) => item.label),
    );
    if (!portLabel) {
        await session.log("No port chosen; keeping any existing saved port.");
        return null;
    }
    return optionByLabel(portItems, portLabel);
}

function optionByLabel(items, label) {
    const found = items.find((item) => item.label === label);
    if (!found) {
        throw new Error(`Unknown selection: ${label}`);
    }
    return found.value;
}

async function pickFirmwareTarget(session) {
    // 3-option flow when a CIRCUITPY drive is auto-detected, 2-option
    // flow otherwise. Always offers "Skip" so the user can prepare
    // firmware files now and copy them manually later without being
    // trapped by an input widget that rejects empty submissions.
    // Returns the chosen drive path string or null when the user
    // skipped. Mirrors pickSerialPort.
    const USE_DETECTED = "use_detected";
    const ENTER_PATH = "enter_path";
    const SKIP = "skip";

    const circuitpy = await detectCircuitPy(session);
    if (circuitpy.detected) {
        await session.log(`Detected CIRCUITPY drive: ${circuitpy.path}`);
    } else {
        await session.log("No mounted CIRCUITPY drive was auto-detected.");
    }

    const options = [];
    if (circuitpy.detected) {
        options.push({
            label: `Install to detected CIRCUITPY drive (${circuitpy.path})`,
            value: USE_DETECTED,
        });
        options.push({ label: "Enter a different drive path…", value: ENTER_PATH });
    } else {
        options.push({ label: "Enter a drive path…", value: ENTER_PATH });
    }
    options.push({
        label: "Skip — prepare firmware files only, copy them manually later",
        value: SKIP,
    });

    const decisionLabel = await session.ui.select(
        "Where should the CircuitPython firmware be installed?",
        options.map((option) => option.label),
    );
    if (!decisionLabel) {
        // Dismiss => skip; do not abort the wizard.
        await session.log(
            "Firmware install target skipped; files will be prepared for manual copy.",
        );
        return null;
    }
    const decision = optionByLabel(options, decisionLabel);
    if (decision === USE_DETECTED) return circuitpy.path;
    if (decision === SKIP) return null;

    // ENTER_PATH: prompt for a drive path. Treat dismissal or empty
    // submission as "skip" so the user is never trapped by a
    // required-field widget. The description names both outcomes.
    const entered = await session.ui.input("CIRCUITPY drive path", {
        title: "CircuitPython target drive",
        description:
            "Full path to the mounted CIRCUITPY drive (e.g. D:/ on Windows or /Volumes/CIRCUITPY on macOS). Dismiss to skip and copy firmware files manually later.",
        default: circuitpy.path || "",
    });
    if (!entered) {
        await session.log(
            "No firmware drive entered; files will be prepared for manual copy.",
        );
        return null;
    }
    return entered;
}

async function collectSelections(session) {
    const options = await loadOptions();
    const scopeLabel = await session.ui.select("Where should the ring work?", [
        "All repositories (recommended)",
        "One repository only",
    ]);
    if (!scopeLabel) return null;

    let repoPath = null;
    if (scopeLabel === "One repository only") {
        repoPath = await session.ui.input("Repository path", {
            title: "Target repository",
            description: "Root directory of the repository where hooks should be deployed.",
            default: process.cwd(),
        });
        if (!repoPath) return null;
    }

    const boardItems = options.boards.map((board) => ({
        label: board.name,
        value: board.id,
        board,
    }));
    const boardLabel = await session.ui.select(
        "Which board are you using?",
        boardItems.map((item) => item.label),
    );
    if (!boardLabel) return null;
    const boardId = optionByLabel(boardItems, boardLabel);
    const board = boardItems.find((item) => item.value === boardId).board;

    const runtimeItems = board.runtimes.map((runtime) => ({
        label:
            runtime.runtime === options.default_runtime
                ? `${runtime.label} (recommended)`
                : runtime.label,
        value: runtime.runtime,
        runtime,
    }));
    const runtimeLabel = await session.ui.select(
        "Which firmware runtime do you want installed?",
        runtimeItems.map((item) => item.label),
    );
    if (!runtimeLabel) return null;
    const runtimeId = optionByLabel(runtimeItems, runtimeLabel);
    const runtime = runtimeItems.find((item) => item.value === runtimeId).runtime;

    const pinDefault = runtime.default_pin || "";
    const pinDescription = runtime.requires_manual_pin
        ? "This board/runtime needs a manual GPIO number for MicroPython."
        : "Use the documented default unless you wired the ring differently.";
    const dataPin = await session.ui.input("NeoPixel data pin", {
        title: "Data pin",
        description: pinDescription,
        default: pinDefault,
    });
    if (dataPin === null) return null;

    const pixelOptions = [
        { label: "24 LEDs — Adafruit NeoPixel Ring 24 (product 1586)", value: 24 },
        { label: "16 LEDs — Adafruit NeoPixel Ring 16 (product 1463)", value: 16 },
        { label: "12 LEDs — Adafruit NeoPixel Ring 12 (product 1643)", value: 12 },
    ];
    const pixelLabel = await session.ui.select(
        "Which ring size do you have?",
        pixelOptions.map((option) => option.label),
    );
    let pixelCount;
    if (!pixelLabel) {
        // Don't abort the entire wizard if the user dismisses this prompt —
        // ring size has a sensible default (24 LEDs, the Adafruit Ring 24).
        // The setup wizard previously silently bailed here, which made it
        // look like the prompt never ran. Fail open instead.
        pixelCount = 24;
        await session.log("Ring size defaulted to 24 LEDs (Adafruit Ring 24).");
    } else {
        pixelCount = pixelOptions.find((option) => option.label === pixelLabel).value;
    }

    const idleOptions = [
        {
            label: "Breathing — stay dim when idle (recommended)",
            value: "breathing",
        },
        { label: "Off — go dark when all sessions end", value: "off" },
    ];
    const idleLabel = await session.ui.select(
        "How should the ring look when Copilot is idle?",
        idleOptions.map((option) => option.label),
    );
    let idleMode;
    if (!idleLabel) {
        // Mirror the ring-size fail-open: dismissed dialogs fall back to the
        // safer default (breathing) so users who hit Esc don't accidentally
        // pick "off" and then wonder why their ring goes dark.
        idleMode = "breathing";
        await session.log(
            'Idle mode defaulted to "breathing" (ring stays dim when idle).',
        );
    } else {
        idleMode = idleOptions.find((option) => option.label === idleLabel).value;
    }

    const autoDetectPort = await session.ui.confirm(
        "Attempt host USB serial auto-detection before setup?",
    );
    let approveFirmware = false;
    let firmwareTarget = null;
    let serialPort = null;
    if (autoDetectPort) {
        const detection = await detectPort(session);
        if (detection.detected) {
            await session.log(`Detected serial device: ${detection.port}`);
        } else {
            await session.log(
                "No matching serial device was auto-detected.",
                { level: "warning" },
            );
        }
        serialPort = await pickSerialPort(session, detection.port || null);
        // Firmware approval is independent of the port choice — CircuitPython
        // firmware copies to the CIRCUITPY drive, which has no relation to the
        // host's data serial port. Even when the user skipped the port choice,
        // they can still approve firmware install.
        approveFirmware = await session.ui.confirm(
            "Approve writing or preparing firmware for this connected board?",
        );
        if (approveFirmware && runtimeId === "circuitpython") {
            firmwareTarget = await pickFirmwareTarget(session);
        }
    }

    return {
        scope: scopeLabel === "One repository only" ? "repo" : "global",
        repo_path: repoPath,
        board_id: boardId,
        runtime: runtimeId,
        data_pin: dataPin || null,
        auto_detect_port: autoDetectPort,
        approve_firmware: approveFirmware,
        firmware_target: firmwareTarget,
        force_hooks: true,
        pixel_count: pixelCount,
        serial_port: serialPort,
        idle_mode: idleMode,
    };
}

async function runSetup(session) {
    if (!session.capabilities.ui?.elicitation) {
        await session.log(
            "Interactive setup UI is unavailable. Run `copilot-command-ring setup-status-ring` in a terminal instead.",
            { level: "warning" },
        );
        return;
    }

    const selections = await collectSelections(session);
    if (!selections) {
        await session.log("Setup canceled.");
        return;
    }

    await session.log(`Running Copilot Command Ring setup (venv: ${venvDir})...`);
    const { stdout, stderr } = await runPython(
        [
            "setup-status-ring",
            "--from-json",
            "-",
            "--yes",
            "--venv-dir",
            venvDir,
            "--package-spec",
            repoRoot,
        ],
        JSON.stringify(selections),
    );
    const output = [stdout.trim(), stderr.trim()].filter(Boolean).join("\n");
    await session.log(output || "Copilot Command Ring setup complete.");
}

async function runDoctor(session) {
    // Pass --config-dir process.cwd() so the doctor evaluates the user's
    // session cwd, not the extension's repoRoot install location -- without
    // this override the doctor would silently load the wrong config file.
    const configDir = process.cwd();
    let result;
    try {
        result = await runPython(["doctor", "--config-dir", configDir], undefined, {
            allowNonZero: true,
        });
    } catch (error) {
        await session.log(`status-ring-doctor failed to launch: ${error.message}`, {
            level: "error",
        });
        return;
    }
    const body = [result.stdout.trim(), result.stderr.trim()]
        .filter(Boolean)
        .join("\n");
    const message = body || "(doctor produced no output)";
    if (result.code === 0) {
        await session.log(message);
    } else {
        await session.log(message, { level: "error" });
    }
}

let session;
session = await joinSession({
    commands: [
        {
            name: "setup-status-ring",
            description: "Guided setup for the Copilot Command Ring status ring",
            handler: async () => {
                try {
                    await runSetup(session);
                } catch (error) {
                    await session.log(`setup-status-ring failed: ${error.message}`, {
                        level: "error",
                    });
                }
            },
        },
        {
            name: "status-ring-doctor",
            description:
                "Health check: verify config, port enumeration, descriptor match, lock state, and send a transient ping",
            handler: async () => {
                await runDoctor(session);
            },
        },
    ],
});
