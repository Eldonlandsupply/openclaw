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

export function loadDotEnv(opts?: { quiet?: boolean }) {
  const quiet = opts?.quiet ?? true;
  const repoEnvPath = path.join(process.cwd(), ".env");
  const allowRepoEnv = parseTruthy(process.env.OPENCLAW_ALLOW_REPO_ENV);
  if (!allowRepoEnv && fs.existsSync(repoEnvPath) && hasRepoMarker(process.cwd())) {
    throw new Error(
      "Refusing to load repo-local .env. Move secrets to ~/.openclaw/.env or set OPENCLAW_ALLOW_REPO_ENV=1 for local-only development.",
    );
  }

  // Load from process CWD first (dotenv default).
  dotenv.config({ quiet });

  // Then load global fallback: ~/.openclaw/.env (or OPENCLAW_STATE_DIR/.env),
  // without overriding any env vars already present.
  const globalEnvPath = path.join(resolveConfigDir(process.env), ".env");
  if (!fs.existsSync(globalEnvPath)) {
    return;
  }

  dotenv.config({ quiet, path: globalEnvPath, override: false });
}
