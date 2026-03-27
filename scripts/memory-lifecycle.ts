import fs from "node:fs/promises";
import path from "node:path";

const MAX_MEMORY_LINES = 220;
const MAX_MEMORY_BYTES = 12 * 1024;
const COMPACT_TRIGGER_LINES = 180;
const COMPACT_TRIGGER_BYTES = 10 * 1024;

type Mode = "check" | "apply";

type CliArgs = {
  workspace: string;
  mode: Mode;
};

function parseArgs(argv: string[]): CliArgs {
  let workspace = process.cwd();
  let mode: Mode = "check";

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--workspace") {
      const next = argv[i + 1];
      if (!next) {
        throw new Error("--workspace requires a value");
      }
      workspace = path.resolve(next);
      i += 1;
      continue;
    }
    if (arg === "--apply") {
      mode = "apply";
      continue;
    }
    if (arg === "--check") {
      mode = "check";
      continue;
    }
  }

  return { workspace, mode };
}

async function fileExists(targetPath: string): Promise<boolean> {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

function summarizeDurable(lines: string[]): string[] {
  const durable = lines
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- ") || /^\d+\./.test(line))
    .slice(0, 40);

  return [
    "# Distilled memory snapshot",
    "",
    `- Generated at ${new Date().toISOString()}.`,
    "- Keep durable facts only. Move one-off logs to memory/YYYY-MM-DD.md.",
    "",
    "## Candidate durable items",
    ...durable,
    "",
  ];
}

async function enforceMemoryLifecycle(args: CliArgs) {
  const memoryPath = path.join(args.workspace, "MEMORY.md");
  if (!(await fileExists(memoryPath))) {
    console.log(`memory-lifecycle: no MEMORY.md at ${memoryPath}`);
    return;
  }

  const raw = await fs.readFile(memoryPath, "utf8");
  const bytes = Buffer.byteLength(raw, "utf8");
  const lines = raw.split(/\r?\n/);
  const lineCount = lines.length;

  const overHardLimit = lineCount > MAX_MEMORY_LINES || bytes > MAX_MEMORY_BYTES;
  const overCompactTrigger = lineCount > COMPACT_TRIGGER_LINES || bytes > COMPACT_TRIGGER_BYTES;

  const archiveDir = path.join(args.workspace, "memory", "archive");
  const archivePath = path.join(archiveDir, `MEMORY-${new Date().toISOString().slice(0, 10)}.md`);

  if (!overHardLimit && !overCompactTrigger) {
    console.log(
      `memory-lifecycle: ok (${lineCount} lines, ${bytes} bytes, limits ${MAX_MEMORY_LINES} lines/${MAX_MEMORY_BYTES} bytes)`,
    );
    return;
  }

  console.log(
    `memory-lifecycle: compaction required (${lineCount} lines, ${bytes} bytes, trigger ${COMPACT_TRIGGER_LINES}/${COMPACT_TRIGGER_BYTES})`,
  );

  if (args.mode === "check") {
    if (overHardLimit) {
      throw new Error(
        `MEMORY.md exceeds hard cap (${lineCount} lines, ${bytes} bytes). Run with --apply to archive and distill.`,
      );
    }
    return;
  }

  await fs.mkdir(archiveDir, { recursive: true });
  await fs.writeFile(archivePath, raw, "utf8");

  const distilled = summarizeDurable(lines).join("\n");
  await fs.writeFile(memoryPath, `${distilled}\n`, "utf8");

  console.log(`memory-lifecycle: archived ${memoryPath} -> ${archivePath}`);
  console.log("memory-lifecycle: wrote distilled MEMORY.md");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  await enforceMemoryLifecycle(args);
}

main().catch((err) => {
  console.error(`memory-lifecycle failed: ${String(err)}`);
  process.exit(1);
});
