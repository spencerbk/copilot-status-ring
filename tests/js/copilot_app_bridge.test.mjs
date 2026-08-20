// SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
// SPDX-License-Identifier: MIT

import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { mkdtemp, mkdir, readFile, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
    buildCommand,
    buildPayload,
    createHookCallbacks,
    detectDesktopHost,
    forwardEvent,
    registerEventSubscriptions,
    wrapperCandidates,
} from "../../host/copilot_command_ring/copilot_app_extension/bridge.mjs";
import {
    loadManagedBridge,
    orchestrateStartup,
    validateMarker,
} from "../../host/copilot_command_ring/copilot_app_extension/extension.mjs";

const SHA = "a".repeat(64);

test("managed marker accepts only exact probe or forwarding schemas", () => {
    const marker = {
        schema_version: 1,
        owner: "copilot-command-ring",
        extension: "copilot-app-status-ring",
        active_bridge_sha256: SHA,
        tracked_releases: [SHA],
        mode: "probe",
    };

    assert.equal(validateMarker(marker).mode, "probe");
    assert.equal(validateMarker({ ...marker, mode: "forwarding" }).mode, "forwarding");
    assert.throws(() => validateMarker({ ...marker, mode: "other" }), /invalid managed/);
    assert.throws(
        () => validateMarker({ ...marker, tracked_releases: [SHA, SHA] }),
        /invalid managed/,
    );
    assert.throws(
        () => validateMarker({ ...marker, unexpected: true }),
        /invalid managed/,
    );
});

test("desktop host detection is exact and fail-inactive", async () => {
    const session = (platform) => ({
        rpc: { mcp: { apps: { getHostContext: async () => ({ context: { platform } }) } } },
    });

    assert.deepEqual(await detectDesktopHost(session("desktop")), {
        active: true,
        platform: "desktop",
        reason: "desktop",
    });
    assert.equal((await detectDesktopHost(session("cli"))).active, false);
    assert.equal((await detectDesktopHost(session(undefined))).active, false);
    assert.match(
        (
            await detectDesktopHost({
                rpc: {
                    mcp: {
                        apps: {
                            getHostContext: async () => {
                                throw new Error("unavailable");
                            },
                        },
                    },
                },
            })
        ).reason,
        /^host-context-unavailable: unavailable$/,
    );
});

test("payload adaptation uses invocation session, cwd alias, ISO dates, and error objects", () => {
    assert.deepEqual(
        buildPayload(
            "errorOccurred",
            {
                sessionId: "input",
                workingDirectory: "/repo",
                timestamp: new Date("2026-08-13T20:00:00Z"),
                error: "boom",
            },
            { sessionId: "invocation" },
        ),
        {
            sessionId: "invocation",
            workingDirectory: "/repo",
            cwd: "/repo",
            timestamp: "2026-08-13T20:00:00.000Z",
            error: { message: "boom" },
        },
    );
});

test("wrapper candidates and commands are cross-platform and ordered", () => {
    assert.deepEqual(
        wrapperCandidates({
            platform: "win32",
            env: { COPILOT_HOME: "C:\\copilot" },
            home: "C:\\Users\\me",
        }),
        [
            "C:\\copilot\\hooks\\run-hook.ps1",
            "C:\\Users\\me\\.copilot\\hooks\\run-hook.ps1",
        ],
    );
    assert.deepEqual(buildCommand("C:\\hook.ps1", "preToolUse", "win32"), {
        executable: "powershell.exe",
        args: [
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "C:\\hook.ps1",
            "preToolUse",
        ],
    });
    assert.deepEqual(buildCommand("/home/me/run-hook.sh", "agentStop", "linux"), {
        executable: "/home/me/run-hook.sh",
        args: ["agentStop"],
    });
});

test("forwarding writes one JSON object, closes stdin, and requests 5000 ms timeout", async () => {
    const child = new EventEmitter();
    let stdin = "";
    let closed = false;
    let timeoutMs;
    child.stdin = {
        end(value) {
            stdin += value;
            closed = true;
            queueMicrotask(() => child.emit("close", 0));
        },
    };

    const result = await forwardEvent("sessionStart", { cwd: "/repo" }, { sessionId: "s1" }, {
        platform: "linux",
        env: { COPILOT_HOME: "/copilot" },
        home: "/home/me",
        existsSync: (candidate) => candidate === "/copilot/hooks/run-hook.sh",
        spawnImpl: () => child,
        setTimer: (callback, milliseconds) => {
            timeoutMs = milliseconds;
            return setTimeout(callback, 1000);
        },
        clearTimer: clearTimeout,
    });

    assert.equal(result, true);
    assert.equal(timeoutMs, 5000);
    assert.equal(closed, true);
    assert.deepEqual(JSON.parse(stdin), { cwd: "/repo", sessionId: "s1" });
    assert.equal(stdin.trim().split("\n").length, 1);
});

test("forwarding catches missing wrappers and spawn failures", async () => {
    assert.equal(
        await forwardEvent("sessionEnd", {}, {}, { existsSync: () => false }),
        false,
    );
    assert.equal(
        await forwardEvent("sessionEnd", {}, {}, {
            existsSync: () => true,
            spawnImpl: () => {
                throw new Error("spawn failed");
            },
        }),
        false,
    );
});

test("forwarding kills only its wrapper child and fails open after 5000 ms", async () => {
    const child = new EventEmitter();
    let killed = false;
    child.stdin = { end() {} };
    child.kill = () => {
        killed = true;
    };

    const result = await forwardEvent("preToolUse", {}, {}, {
        existsSync: () => true,
        spawnImpl: () => child,
        setTimer: (callback, milliseconds) => {
            assert.equal(milliseconds, 5000);
            queueMicrotask(callback);
            return 1;
        },
        clearTimer: () => {},
    });

    assert.equal(result, false);
    assert.equal(killed, true);
});

test("stdin errors kill the direct wrapper child and fail open", async () => {
    const child = new EventEmitter();
    const stdin = new EventEmitter();
    let killed = false;
    stdin.end = () => queueMicrotask(() => stdin.emit("error", new Error("EPIPE")));
    child.stdin = stdin;
    child.kill = () => {
        killed = true;
    };

    const result = await forwardEvent("preToolUse", {}, {}, {
        existsSync: () => true,
        spawnImpl: () => child,
        setTimer: () => 1,
        clearTimer: () => {},
    });

    assert.equal(result, false);
    assert.equal(killed, true);
});

test("all SDK hooks map exactly and resolve null", async () => {
    const calls = [];
    const hooks = createHookCallbacks(async (...args) => {
        calls.push(args);
        return false;
    });
    const expected = {
        onSessionStart: "sessionStart",
        onUserPromptSubmitted: "userPromptSubmitted",
        onPreToolUse: "preToolUse",
        onPostToolUse: "postToolUse",
        onPostToolUseFailure: "postToolUseFailure",
        onErrorOccurred: "errorOccurred",
        onAgentStop: "agentStop",
        onSessionEnd: "sessionEnd",
    };

    assert.deepEqual(Object.keys(hooks), Object.keys(expected));
    for (const [hookName, eventName] of Object.entries(expected)) {
        assert.equal(await hooks[hookName]({ value: 1 }, { sessionId: "s" }), null);
        assert.equal(calls.at(-1)[0], eventName);
    }
});

test("event subscriptions map permission, compaction, and aborted idle only", async () => {
    const handlers = new Map();
    const calls = [];
    const session = {
        on(name, callback) {
            handlers.set(name, callback);
        },
    };
    registerEventSubscriptions(session, async (...args) => {
        calls.push(args);
        throw new Error("fail open");
    });

    assert.deepEqual([...handlers.keys()], [
        "permission.requested",
        "session.compaction_start",
        "session.idle",
    ]);
    assert.equal(await handlers.get("permission.requested")({ data: { sessionId: "s" } }), null);
    assert.equal(calls[0][0], "notification");
    assert.equal(calls[0][1].notification_type, "permission_prompt");
    assert.equal(await handlers.get("session.compaction_start")({ data: {} }), null);
    assert.equal(calls[1][0], "preCompact");
    assert.equal("trigger" in calls[1][1], false);
    assert.equal(await handlers.get("session.idle")({ data: { aborted: false } }), null);
    assert.equal(calls.length, 2);
    assert.equal(await handlers.get("session.idle")({ data: { aborted: true } }), null);
    assert.equal(calls[2][0], "agentStop");
    assert.equal(calls[2][1].stopReason, "aborted");
});

test("startup buffers pre-detection hooks and drains once for desktop", async () => {
    const forwarded = [];
    const bridge = {
        createHookCallbacks,
        detectDesktopHost: async () => ({
            active: true,
            platform: "desktop",
            reason: "desktop",
        }),
        forwardEvent: async (...args) => {
            forwarded.push(args);
            return true;
        },
        registerEventSubscriptions() {},
    };
    const joinSessionImpl = async ({ hooks }) => {
        assert.equal(
            await hooks.onSessionStart({ workingDirectory: "/repo" }, { sessionId: "s1" }),
            null,
        );
        return {};
    };

    const result = await orchestrateStartup({
        marker: { mode: "forwarding" },
        bridge,
        joinSessionImpl,
    });

    assert.equal(result.active, true);
    assert.deepEqual(forwarded, [
        ["sessionStart", { workingDirectory: "/repo" }, { sessionId: "s1" }],
    ]);
});

test("startup discards pre-detection hooks for non-desktop", async () => {
    const forwarded = [];
    const bridge = {
        createHookCallbacks,
        detectDesktopHost: async () => ({
            active: false,
            platform: "cli",
            reason: "non-desktop-or-missing",
        }),
        forwardEvent: async (...args) => {
            forwarded.push(args);
            return true;
        },
        registerEventSubscriptions() {},
    };
    const joinSessionImpl = async ({ hooks }) => {
        assert.equal(await hooks.onSessionStart({}, { sessionId: "s1" }), null);
        return {};
    };

    const result = await orchestrateStartup({
        marker: { mode: "forwarding" },
        bridge,
        joinSessionImpl,
    });

    assert.equal(result.active, false);
    assert.deepEqual(forwarded, []);
});

test("probe startup installs no hooks or subscriptions", async () => {
    let subscriptions = 0;
    const bridge = {
        detectDesktopHost: async () => ({
            active: true,
            platform: "desktop",
            reason: "desktop",
        }),
        registerEventSubscriptions: () => {
            subscriptions += 1;
        },
    };
    const optionsSeen = [];

    const result = await orchestrateStartup({
        marker: { mode: "probe" },
        bridge,
        joinSessionImpl: async (options) => {
            optionsSeen.push(options);
            return {};
        },
    });

    assert.equal(result.active, true);
    assert.deepEqual(optionsSeen, [{}]);
    assert.equal(subscriptions, 0);
});

test("managed loader verifies bridge bytes before importing exact release path", async () => {
    const extensionDir = await mkdtemp(path.join(os.tmpdir(), "ring-loader-"));
    const releaseDir = path.join(extensionDir, "releases", SHA);
    const bridgeBytes = Buffer.from("export const verified = true;\n");
    const marker = {
        schema_version: 1,
        owner: "copilot-command-ring",
        extension: "copilot-app-status-ring",
        active_bridge_sha256: SHA,
        tracked_releases: [SHA],
        mode: "probe",
    };
    await mkdir(releaseDir, { recursive: true });
    await writeFile(
        path.join(extensionDir, ".copilot-command-ring-managed.json"),
        JSON.stringify(marker),
    );
    await writeFile(path.join(releaseDir, "bridge.mjs"), bridgeBytes);
    const imported = [];

    await assert.rejects(
        loadManagedBridge(extensionDir, async (url) => {
            imported.push(url);
            return {};
        }),
        /SHA-256 mismatch/,
    );
    assert.deepEqual(imported, []);

    const crypto = await import("node:crypto");
    marker.active_bridge_sha256 = crypto
        .createHash("sha256")
        .update(bridgeBytes)
        .digest("hex");
    marker.tracked_releases = [marker.active_bridge_sha256];
    const validRelease = path.join(
        extensionDir,
        "releases",
        marker.active_bridge_sha256,
    );
    await mkdir(validRelease);
    await writeFile(path.join(validRelease, "bridge.mjs"), bridgeBytes);
    await writeFile(
        path.join(extensionDir, ".copilot-command-ring-managed.json"),
        JSON.stringify(marker),
    );

    const loaded = await loadManagedBridge(extensionDir, async (url) => {
        imported.push(url);
        return { url };
    });

    assert.equal(imported.length, 1);
    assert.equal(path.dirname(fileURLToPath(imported[0])), validRelease);
    assert.equal((await readFile(path.join(validRelease, "bridge.mjs"))).compare(bridgeBytes), 0);
    assert.equal(loaded.marker.mode, "probe");
});

test("managed loader rejects symbolic or junction managed path components", async () => {
    const extensionDir = await mkdtemp(path.join(os.tmpdir(), "ring-loader-link-"));
    const outside = await mkdtemp(path.join(os.tmpdir(), "ring-loader-outside-"));
    await mkdir(path.join(outside, SHA));
    await writeFile(path.join(outside, SHA, "bridge.mjs"), "export {};\n");
    await symlink(
        outside,
        path.join(extensionDir, "releases"),
        process.platform === "win32" ? "junction" : "dir",
    );
    await writeFile(
        path.join(extensionDir, ".copilot-command-ring-managed.json"),
        JSON.stringify({
            schema_version: 1,
            owner: "copilot-command-ring",
            extension: "copilot-app-status-ring",
            active_bridge_sha256: SHA,
            tracked_releases: [SHA],
            mode: "probe",
        }),
    );

    await assert.rejects(loadManagedBridge(extensionDir, async () => ({})), /unsafe managed/);
});
