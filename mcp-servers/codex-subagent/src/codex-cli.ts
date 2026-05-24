import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { mkdtemp, readFile, rm } from "node:fs/promises";

export async function isCodexAvailable(): Promise<boolean> {
  return new Promise((resolve) => {
    const proc = spawn("codex", ["--version"], { stdio: ["ignore", "pipe", "pipe"], timeout: 5000 });
    proc.on("error", () => resolve(false));
    proc.on("close", (code) => resolve(code === 0));
  });
}

export interface CodexExecOptions {
  prompt: string;
  cwd?: string;
  addDirs?: string[];
  sandbox?: "read-only" | "workspace-write" | "danger-full-access";
  model?: string;
  reasoningEffort?: "low" | "medium" | "high" | "xhigh";
  skipGitCheck?: boolean;
  timeout?: number;
  ephemeral?: boolean;
}

export interface CodexExecResult {
  exitCode: number;
  lastMessage: string;
  events: CodexEvent[];
  error?: string;
}

export interface CodexEvent {
  type: string;
  [key: string]: unknown;
}

export async function runCodexAgent(options: CodexExecOptions): Promise<CodexExecResult> {
  const {
    prompt,
    cwd = process.cwd(),
    addDirs = [],
    sandbox = "danger-full-access",
    model = "gpt-5.5",
    reasoningEffort = "xhigh",
    skipGitCheck = false,
    timeout = 900_000,
    ephemeral = true,
  } = options;

  const tempDir = await mkdtemp(join(tmpdir(), "codex-subagent-"));
  const outputFile = join(tempDir, "last-message.txt");

  const args: string[] = ["exec"];

  args.push("-s", sandbox);
  args.push("-C", cwd);
  args.push("-o", outputFile);
  args.push("--json");
  args.push("-c", `model_reasoning_effort="${reasoningEffort}"`);

  if (skipGitCheck) args.push("--skip-git-repo-check");
  if (ephemeral) args.push("--ephemeral");
  if (model) args.push("-m", model);
  for (const dir of addDirs) {
    args.push("--add-dir", dir);
  }

  args.push(prompt);

  console.error(`[codex-subagent] codex exec -m ${model} -s ${sandbox} effort=${reasoningEffort} cwd=${cwd}`);

  // Pre-flight: verify codex CLI is reachable before committing to the long
  // call. Without this, a broken `codex` install (auth missing, binary not on
  // PATH, version probe hanging) wedges the caller — see GitHub Issue #7.
  // The probe has its own 5 s timeout via isCodexAvailable.
  const reachable = await isCodexAvailable();
  if (!reachable) {
    return {
      exitCode: 127,
      lastMessage: "",
      events: [],
      error:
        "codex CLI is not reachable on this host (binary missing, auth expired, " +
        "or `codex --version` hung past 5 s). Cannot dispatch the requested task.",
    };
  }

  return new Promise((resolve) => {
    const proc = spawn("codex", args, {
      stdio: ["ignore", "pipe", "pipe"],
      env: process.env,
      timeout,
    });

    const events: CodexEvent[] = [];
    let stdout = "";
    let stderr = "";
    let resolved = false;

    // Single resolve guard so neither the watchdog nor the close/error paths
    // race each other on a wedged process. Whichever fires first wins; the
    // others are no-ops. This is the v15.8 hardening for Issue #7 — without
    // it, a process that spawns but never emits events (e.g. codex auth
    // hanging at startup) leaves the MCP call wedged forever because Node's
    // spawn `timeout` option only fires for processes that actually spawned
    // *and* whose event-loop ticks reach the kill signal.
    function done(result: CodexExecResult): void {
      if (resolved) return;
      resolved = true;
      cleanup(tempDir);
      resolve(result);
    }

    proc.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stdout += text;
      for (const line of text.split("\n")) {
        if (!line.trim()) continue;
        try {
          const event = JSON.parse(line) as CodexEvent;
          events.push(event);
        } catch {
          // non-JSON line, ignore
        }
      }
    });

    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    proc.on("error", (err) => {
      done({
        exitCode: 1,
        lastMessage: "",
        events,
        error: `Failed to spawn codex: ${err.message}`,
      });
    });

    proc.on("close", async (code) => {
      let lastMessage = "";
      try {
        lastMessage = await readFile(outputFile, "utf-8");
      } catch {
        // output file may not exist if codex crashed early
        lastMessage = extractLastMessageFromEvents(events) || stderr.slice(-2000);
      }
      done({
        exitCode: code ?? 1,
        lastMessage,
        events,
        error: code !== 0 ? stderr.slice(-1000) : undefined,
      });
    });

    // Watchdog: force-resolve with a timeout marker even if proc events are
    // silent. We add a 10 s grace beyond the requested `timeout` so the
    // SIGTERM/SIGKILL ladder has room to land. After the grace, the wrapper
    // gives up on the process events entirely and returns.
    const sigtermAt = setTimeout(() => {
      try {
        proc.kill("SIGTERM");
      } catch {
        // proc may already be gone
      }
    }, timeout);
    const sigkillAt = setTimeout(() => {
      try {
        proc.kill("SIGKILL");
      } catch {
        // proc may already be gone
      }
    }, timeout + 5_000);
    const watchdogAt = setTimeout(() => {
      done({
        exitCode: 124, // GNU timeout(1) convention
        lastMessage: extractLastMessageFromEvents(events) || stderr.slice(-2000),
        events,
        error:
          `codex did not return within ${Math.round(timeout / 1000)}s ` +
          `(SIGTERM+SIGKILL sent). Treat as a hang; the MCP wrapper has ` +
          `force-resolved to keep the parent Role from wedging.`,
      });
    }, timeout + 10_000);

    // Clear the watchdog timers when proc completes naturally so we don't
    // leak handles in a long-lived MCP server.
    proc.on("close", () => {
      clearTimeout(sigtermAt);
      clearTimeout(sigkillAt);
      clearTimeout(watchdogAt);
    });
    proc.on("error", () => {
      clearTimeout(sigtermAt);
      clearTimeout(sigkillAt);
      clearTimeout(watchdogAt);
    });
  });
}

function extractLastMessageFromEvents(events: CodexEvent[]): string {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type === "message" && typeof e.content === "string") return e.content;
    if (e.type === "agent_message" && typeof e.text === "string") return e.text;
  }
  return "";
}

async function cleanup(dir: string): Promise<void> {
  try {
    await rm(dir, { recursive: true, force: true });
  } catch {
    // best effort
  }
}

export function summarizeEvents(events: CodexEvent[]): {
  filesChanged: string[];
  commandsRun: Array<{ command: string; exitCode?: number; output?: string }>;
  messages: string[];
  usage?: { input_tokens: number; output_tokens: number; cached_input_tokens?: number };
} {
  const filesChanged = new Set<string>();
  const commandsRun: Array<{ command: string; exitCode?: number; output?: string }> = [];
  const messages: string[] = [];
  let usage: { input_tokens: number; output_tokens: number; cached_input_tokens?: number } | undefined;

  for (const e of events) {
    // codex exec --json format: item.completed events
    if (e.type === "item.completed") {
      const item = e.item as Record<string, unknown> | undefined;
      if (!item) continue;

      if (item.type === "file_change") {
        const changes = item.changes as Array<{ path?: string; kind?: string }> | undefined;
        if (changes) {
          for (const c of changes) {
            if (c.path) filesChanged.add(c.path);
          }
        }
      }

      if (item.type === "command_execution") {
        commandsRun.push({
          command: (item.command || "") as string,
          exitCode: item.exit_code as number | undefined,
          output: item.aggregated_output as string | undefined,
        });
      }

      if (item.type === "agent_message") {
        if (typeof item.text === "string") messages.push(item.text);
      }
    }

    if (e.type === "turn.completed") {
      const u = e.usage as Record<string, number> | undefined;
      if (u) {
        usage = {
          input_tokens: u.input_tokens || 0,
          output_tokens: u.output_tokens || 0,
          cached_input_tokens: u.cached_input_tokens,
        };
      }
    }
  }

  return { filesChanged: [...filesChanged], commandsRun, messages, usage };
}
