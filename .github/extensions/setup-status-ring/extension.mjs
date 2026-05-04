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

function runPythonCandidate(candidate, args, input) {
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
                    const wrapped = new Error(stderr || error.message);
                    wrapped.code = error.code;
                    reject(wrapped);
                    return;
                }
                resolve({ stdout, stderr });
            },
        );
        if (input !== undefined) {
            child.stdin.end(input);
        }
    });
}

async function runPython(args, input) {
    let lastError;
    for (const candidate of pythonCandidates) {
        try {
            return await runPythonCandidate(candidate, args, input);
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

function optionByLabel(items, label) {
    const found = items.find((item) => item.label === label);
    if (!found) {
        throw new Error(`Unknown selection: ${label}`);
    }
    return found.value;
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

    const autoDetectPort = await session.ui.confirm(
        "Attempt host USB serial auto-detection before setup?",
    );
    let approveFirmware = false;
    let firmwareTarget = null;
    if (autoDetectPort) {
        const detection = await detectPort(session);
        if (detection.detected) {
            await session.log(`Detected serial device: ${detection.port}`);
            approveFirmware = await session.ui.confirm(
                "Approve writing or preparing firmware for this connected board?",
            );
            if (approveFirmware && runtimeId === "circuitpython") {
                const circuitpy = await detectCircuitPy(session);
                firmwareTarget = await session.ui.input("CIRCUITPY drive path", {
                    title: "CircuitPython target drive",
                    description:
                        "Leave blank to prepare firmware only and copy it manually later.",
                    default: circuitpy.path || "",
                });
                if (firmwareTarget === "") firmwareTarget = null;
            }
        } else {
            await session.log("No matching serial device was detected; firmware upload stays manual.", {
                level: "warning",
            });
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
    ],
});
