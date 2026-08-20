// SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
// SPDX-License-Identifier: MIT

import { createHash } from "node:crypto";
import { lstat, readFile, realpath } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const extensionDir = path.dirname(fileURLToPath(import.meta.url));
const hashPattern = /^[0-9a-f]{64}$/;

export function validateMarker(value) {
    const expectedKeys = [
        "active_bridge_sha256",
        "extension",
        "mode",
        "owner",
        "schema_version",
        "tracked_releases",
    ];
    if (
        !value ||
        typeof value !== "object" ||
        Object.keys(value).sort().join(",") !== expectedKeys.join(",") ||
        value.schema_version !== 1 ||
        value.owner !== "copilot-command-ring" ||
        value.extension !== "copilot-app-status-ring" ||
        !hashPattern.test(value.active_bridge_sha256) ||
        !Array.isArray(value.tracked_releases) ||
        value.tracked_releases.length === 0 ||
        value.tracked_releases.some((release) => !hashPattern.test(release)) ||
        new Set(value.tracked_releases).size !== value.tracked_releases.length ||
        !value.tracked_releases.includes(value.active_bridge_sha256) ||
        !["probe", "forwarding"].includes(value.mode)
    ) {
        throw new Error("invalid managed extension marker");
    }
    return value;
}

async function requireManagedPath(managedPath, kind) {
    let info;
    try {
        info = await lstat(managedPath);
    } catch (error) {
        throw new Error(`unsafe managed ${kind} path ${managedPath}: ${error.message}`);
    }
    const validType = kind === "directory" ? info.isDirectory() : info.isFile();
    if (info.isSymbolicLink() || !validType) {
        throw new Error(`unsafe managed ${kind} path ${managedPath}`);
    }
}

export async function loadManagedBridge(
    managedExtensionDir,
    importModule = async (url) => import(url),
) {
    const managedMarkerPath = path.join(
        managedExtensionDir,
        ".copilot-command-ring-managed.json",
    );
    await requireManagedPath(managedMarkerPath, "file");
    const marker = validateMarker(
        JSON.parse(await readFile(managedMarkerPath, "utf8")),
    );
    const releasesDir = path.join(managedExtensionDir, "releases");
    const releaseDir = path.join(releasesDir, marker.active_bridge_sha256);
    const bridgePath = path.join(releaseDir, "bridge.mjs");
    await requireManagedPath(releasesDir, "directory");
    await requireManagedPath(releaseDir, "directory");
    await requireManagedPath(bridgePath, "file");

    const [resolvedReleaseDir, resolvedBridgePath] = await Promise.all([
        realpath(releaseDir),
        realpath(bridgePath),
    ]);
    if (path.dirname(resolvedBridgePath) !== resolvedReleaseDir) {
        throw new Error("managed bridge escaped its active release directory");
    }
    const bridgeBytes = await readFile(resolvedBridgePath);
    const actualSha256 = createHash("sha256").update(bridgeBytes).digest("hex");
    if (actualSha256 !== marker.active_bridge_sha256) {
        throw new Error(
            `managed bridge SHA-256 mismatch: expected ${marker.active_bridge_sha256}, ` +
                `found ${actualSha256}`,
        );
    }
    const bridgeUrl = pathToFileURL(resolvedBridgePath);
    const bridge = await importModule(bridgeUrl.href);
    return { marker, bridge, bridgePath: resolvedBridgePath };
}

export async function orchestrateStartup({
    marker,
    bridge,
    joinSessionImpl,
    debug = process.env.COPILOT_RING_APP_DEBUG === "1",
} = {}) {
    const pending = [];
    let forwardingState = "pending";
    const forward = async (eventName, input, invocation) => {
        if (forwardingState === "pending" || forwardingState === "draining") {
            pending.push([eventName, input, invocation]);
            return false;
        }
        if (forwardingState !== "active") return false;
        try {
            return await bridge.forwardEvent(eventName, input, invocation);
        } catch {
            return false;
        }
    };
    const options =
        marker.mode === "forwarding"
            ? { hooks: bridge.createHookCallbacks(forward) }
            : {};
    const session = await joinSessionImpl(options);
    const detection = await bridge.detectDesktopHost(session);

    if (marker.mode === "forwarding" && detection.active) {
        forwardingState = "draining";
        while (pending.length > 0) {
            const args = pending.shift();
            try {
                await bridge.forwardEvent(...args);
            } catch {
                // Never affect Copilot behavior.
            }
        }
        forwardingState = "active";
        bridge.registerEventSubscriptions(session, forward);
    } else {
        pending.length = 0;
        forwardingState = "inactive";
    }

    if (debug) {
        console.error(
            `[copilot-command-ring] app-extension discovered platform=${
                detection.platform ?? "missing"
            } active=${detection.active} mode=${marker.mode}`,
        );
    }
    return detection;
}

export async function startManagedExtension({
    managedExtensionDir = extensionDir,
    joinSessionImpl,
    importModule,
} = {}) {
    const { marker, bridge } = await loadManagedBridge(
        managedExtensionDir,
        importModule,
    );
    let join = joinSessionImpl;
    if (!join) {
        ({ joinSession: join } = await import("@github/copilot-sdk/extension"));
    }
    return orchestrateStartup({
        marker,
        bridge,
        joinSessionImpl: join,
    });
}

try {
    await startManagedExtension();
} catch (error) {
    if (process.env.COPILOT_RING_APP_DEBUG === "1") {
        console.error(
            `[copilot-command-ring] app-extension inactive reason=${
                error?.message ?? String(error)
            }`,
        );
    }
}
