import dotenv from "dotenv";
import fs from "node:fs";
import path from "node:path";
import { resolveConfigDir } from "../utils.js";

function parseTruthy(value: string | undefined): boolean {
  const normalized = value?.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}

function hasRepoMarker(dir: string): boolean {
  return fs.existsSync(path.join(dir, ".git"));
}

function assertReadableFile(filePath: string, label: string): void {
  if (!fs.existsSync(filePath)) {
    return;
  }

  try {
    fs.accessSync(filePath, fs.constants.R_OK);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(
      `${label} exists but is not readable by this process: ${filePath}. ${detail}.` +
        " Fix ownership/permissions before starting OpenClaw.",
      { cause: error },
    );
  }
}

function loadDotenvFile(filePath: string, quiet: boolean, override: boolean, label: string): void {
  if (!fs.existsSync(filePath)) {
    return;
  }
  assertReadableFile(filePath, label);
  const result = dotenv.config({ quiet, path: filePath, override });
  if (result.error) {
    throw new Error(`Failed to parse ${label}: ${filePath}. ${result.error.message}`);
  }
}

export function loadDotEnv(opts?: { quiet?: boolean }) {
  const quiet = opts?.quiet ?? true;
  const repoEnvPath = path.join(process.cwd(), ".env");
  const allowRepoEnv = parseTruthy(process.env.OPENCLAW_ALLOW_REPO_ENV);
  if (!allowRepoEnv && fs.existsSync(repoEnvPath) && hasRepoMarker(process.cwd())) {
    throw new Error(
      "Refusing to load repo-local .env. Move secrets to ~/.openclaw/.env or set OPENCLAW_ALLOW_REPO_ENV=1 for local-only development.",
    );
  }

  // Load from process CWD first (dotenv default path), if present.
  loadDotenvFile(repoEnvPath, quiet, false, "CWD .env");

  // Then load global fallback: ~/.openclaw/.env (or OPENCLAW_STATE_DIR/.env),
  // without overriding any env vars already present.
  const globalEnvPath = path.join(resolveConfigDir(process.env), ".env");
  if (!fs.existsSync(globalEnvPath)) {
    return;
  }

  loadDotenvFile(globalEnvPath, quiet, false, "global .env");
}
