import readline from "node:readline";
import { stdin, stdout } from "node:process";

let Codex;
try {
  ({ Codex } = await import("@openai/codex-sdk"));
} catch (error) {
  write({
    type: "fatal",
    ok: false,
    error:
      "Cannot import @openai/codex-sdk. Install it with `npm install @openai/codex-sdk` in the MetaLoop environment.",
    detail: String(error && error.message ? error.message : error),
  });
  process.exit(1);
}

const rl = readline.createInterface({ input: stdin, crlfDelay: Infinity });
let codex = null;
let thread = null;
let threadId = "";

function write(payload) {
  stdout.write(JSON.stringify(payload) + "\n");
}

function threadIdentifier(candidate) {
  if (!candidate || typeof candidate !== "object") {
    return "";
  }
  return String(candidate.id || candidate.threadId || candidate.thread_id || "");
}

async function ensureThread(request) {
  if (!codex) {
    const config = {};
    if (request.approvalPolicy) {
      config.approval_policy = request.approvalPolicy;
    }
    if (request.networkAccess !== undefined) {
      config.sandbox_workspace_write = { network_access: Boolean(request.networkAccess) };
    }
    codex = new Codex({ config });
  }
  if (thread) {
    return;
  }
  if (request.threadId) {
    thread = codex.resumeThread(request.threadId);
  } else {
    const options = {};
    if (request.workingDirectory) {
      options.workingDirectory = request.workingDirectory;
    }
    if (request.skipGitRepoCheck !== undefined) {
      options.skipGitRepoCheck = Boolean(request.skipGitRepoCheck);
    }
    if (request.model) {
      options.model = request.model;
    }
    if (request.sandboxMode) {
      options.sandboxMode = request.sandboxMode;
    }
    if (request.approvalPolicy) {
      options.approvalPolicy = request.approvalPolicy;
    }
    if (request.networkAccess !== undefined) {
      options.networkAccessEnabled = Boolean(request.networkAccess);
    }
    thread = codex.startThread(options);
  }
  threadId = threadIdentifier(thread) || request.threadId || threadId;
}

async function handle(request) {
  await ensureThread(request);
  if (request.type === "init") {
    write({ id: request.id, ok: true, threadId });
    return;
  }
  if (request.type !== "run") {
    write({ id: request.id, ok: false, error: `Unsupported request type: ${request.type}` });
    return;
  }
  const runOptions = {};
  if (request.outputSchema) {
    runOptions.outputSchema = request.outputSchema;
  }
  const turn = await thread.run(request.prompt, runOptions);
  const finalResponse = String(turn.finalResponse ?? turn.final_response ?? turn.finalMessage ?? "");
  threadId = threadIdentifier(turn) || threadIdentifier(thread) || threadId;
  write({
    id: request.id,
    ok: true,
    threadId,
    finalResponse,
    items: turn.items ?? [],
    usage: turn.usage ?? null,
  });
}

for await (const line of rl) {
  if (!line.trim()) {
    continue;
  }
  let request;
  try {
    request = JSON.parse(line);
  } catch (error) {
    write({ ok: false, error: `Invalid bridge JSON: ${error.message}` });
    continue;
  }
  try {
    await handle(request);
  } catch (error) {
    write({
      id: request.id,
      ok: false,
      threadId,
      error: String(error && error.message ? error.message : error),
    });
  }
}
