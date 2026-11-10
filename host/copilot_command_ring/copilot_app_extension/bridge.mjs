// SPDX-FileCopyrightText: 2024 Copilot Status Ring Contributors
// SPDX-License-Identifier: MIT

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";

export const FORWARD_TIMEOUT_MS = 5000;

export async function detectDesktopHost(session) {
    try {
        const result = await session.rpc.mcp.apps.getHostContext();
        const platform = result?.context?.platform ?? null;
        return {
            active: platform === "desktop",
            platform,
            reason: platform === "desktop" ? "desktop" : "non-desktop-or-missing",
        };
    } catch (error) {
        return {
            active: false,
            platform: null,
            reason: `host-context-unavailable: ${error?.message ?? String(error)}`,
        };
    }
}

export function buildPayload(eventName, input = {}, invocation = {}) {
    const payload = {
        ...input,
        sessionId: invocation?.sessionId ?? input?.sessionId,
        cwd: input?.workingDirectory ?? input?.cwd,
        timestamp:
            input?.timestamp instanceof Date
                ? input.timestamp.toISOString()
                : input?.timestamp,
    };
    if (eventName === "errorOccurred" && typeof payload.error === "string") {
        payload.error = { message: payload.error };
    }
    for (const key of Object.keys(payload)) {
        if (payload[key] === undefined) delete payload[key];
    }
    return payload;
}

export function wrapperCandidates({
    platform = process.platform,
    env = process.env,
    home = os.homedir(),
} = {}) {
    const paths = platform === "win32" ? path.win32 : path.posix;
    const wrapper = platform === "win32" ? "run-hook.ps1" : "run-hook.sh";
    const roots = [];
    if (env.COPILOT_HOME) roots.push(env.COPILOT_HOME);
    roots.push(paths.join(home, ".copilot"));
    return [...new Set(roots.map((root) => paths.join(root, "hooks", wrapper)))];
}

export function buildCommand(wrapper, eventName, platform = process.platform) {
    if (platform === "win32") {
        return {
            executable: "powershell.exe",
            args: [
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                wrapper,
                eventName,
            ],
        };
    }
    return { executable: wrapper, args: [eventName] };
}

export async function forwardEvent(
    eventName,
    input,
    invocation,
    {
        platform = process.platform,
        env = process.env,
        home = os.homedir(),
        existsSync: pathExists = existsSync,
        spawnImpl = spawn,
        setTimer = setTimeout,
        clearTimer = clearTimeout,
    } = {},
) {
    try {
        const wrapper = wrapperCandidates({ platform, env, home }).find(pathExists);
        if (!wrapper) return false;
        const command = buildCommand(wrapper, eventName, platform);
        const payload = JSON.stringify(buildPayload(eventName, input, invocation));
        return await new Promise((resolve) => {
            let settled = false;
            let child;
            const finish = (result) => {
                if (settled) return;
                settled = true;
                clearTimer(timer);
                resolve(result);
            };
            const killAndFinish = () => {
                try {
                    child?.kill();
                } catch {
                    // The forwarding boundary is always fail-open.
                }
                finish(false);
            };
            try {
                child = spawnImpl(command.executable, command.args, {
                    stdio: ["pipe", "ignore", "ignore"],
                    windowsHide: true,
                });
            } catch {
                resolve(false);
                return;
            }
            const timer = setTimer(killAndFinish, FORWARD_TIMEOUT_MS);
            child.once("error", () => finish(false));
            child.once("close", (code) => finish(code === 0));
            child.stdin.once?.("error", killAndFinish);
            child.stdin.end(payload);
        });
    } catch {
        return false;
    }
}

const HOOK_EVENTS = {
    onSessionStart: "sessionStart",
    onUserPromptSubmitted: "userPromptSubmitted",
    onPreToolUse: "preToolUse",
    onPostToolUse: "postToolUse",
    onPostToolUseFailure: "postToolUseFailure",
    onErrorOccurred: "errorOccurred",
    onAgentStop: "agentStop",
    onSessionEnd: "sessionEnd",
};

export function createHookCallbacks(forward) {
    return Object.fromEntries(
        Object.entries(HOOK_EVENTS).map(([hookName, eventName]) => [
            hookName,
            async (input, invocation) => {
                try {
                    await forward(eventName, input, invocation);
                } catch {
                    // Never affect Copilot behavior.
                }
                return null;
            },
        ]),
    );
}

export function registerEventSubscriptions(session, forward) {
    session.on("permission.requested", async (event) => {
        try {
            await forward(
                "notification",
                { ...(event?.data ?? {}), notification_type: "permission_prompt" },
                event,
            );
        } catch {
            // Never affect Copilot behavior.
        }
        return null;
    });
    session.on("session.compaction_start", async (event) => {
        try {
            await forward("preCompact", { ...(event?.data ?? {}) }, event);
        } catch {
            // Never affect Copilot behavior.
        }
        return null;
    });
    session.on("session.idle", async (event) => {
        if (event?.data?.aborted === true) {
            try {
                await forward(
                    "agentStop",
                    { ...event.data, stopReason: "aborted" },
                    event,
                );
            } catch {
                // Never affect Copilot behavior.
            }
        }
        return null;
    });
}
