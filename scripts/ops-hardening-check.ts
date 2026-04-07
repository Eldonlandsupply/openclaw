import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const REPO_ROOT = process.cwd();
const execFileAsync = promisify(execFile);

const CRITICAL_SHELL_FILES = ["scripts/auth-monitor.sh", "scripts/termux-auth-widget.sh"];

const PIPELINE_RE = /(^|[^|])\|([^|]|$)/;

function isCommentOrEmpty(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.length === 0 || trimmed.startsWith("#");
}

async function main() {
  const failures: string[] = [];

  try {
    await execFileAsync("git", ["ls-files", "--error-unmatch", ".env"], { cwd: REPO_ROOT });
    failures.push(
      ".env is tracked in git, remove it from version control and keep secrets in local-only files",
    );
  } catch {
    // Expected: .env should not be tracked.
  }

  for (const relPath of CRITICAL_SHELL_FILES) {
    const absPath = path.join(REPO_ROOT, relPath);
    const text = await fs.readFile(absPath, "utf8");
    const lines = text.split(/\r?\n/);
    lines.forEach((line, idx) => {
      if (isCommentOrEmpty(line)) {
        return;
      }
      if (!line.includes("|")) {
        return;
      }
      const trimmed = line.trim();
      if (trimmed.startsWith("case ") || trimmed.includes(")") || trimmed.includes(";;")) {
        return;
      }
      const normalized = line.replace(/\|\|/g, "");
      if (PIPELINE_RE.test(normalized)) {
        failures.push(`${relPath}:${idx + 1}: pipeline operator found in critical script`);
      }
    });
  }

  if (failures.length > 0) {
    console.error("ops-hardening check failed");
    for (const failure of failures) {
      console.error(`- ${failure}`);
    }
    process.exit(1);
  }

  console.log("ops-hardening check passed");
}

main().catch((err) => {
  console.error(`ops-hardening check failed: ${String(err)}`);
  process.exit(1);
});
