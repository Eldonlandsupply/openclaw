import fsSync from "node:fs";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import { loadDotEnv } from "./dotenv.js";

async function writeEnvFile(filePath: string, contents: string) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, contents, "utf8");
}

describe("loadDotEnv", () => {
  it("loads ~/.openclaw/.env as fallback without overriding CWD .env", async () => {
    const prevEnv = { ...process.env };
    const prevCwd = process.cwd();

    const base = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-dotenv-test-"));
    const cwdDir = path.join(base, "cwd");
    const stateDir = path.join(base, "state");

    process.env.OPENCLAW_STATE_DIR = stateDir;

    await writeEnvFile(path.join(stateDir, ".env"), "FOO=from-global\nBAR=1\n");
    await writeEnvFile(path.join(cwdDir, ".env"), "FOO=from-cwd\n");

    process.chdir(cwdDir);
    delete process.env.FOO;
    delete process.env.BAR;

    loadDotEnv({ quiet: true });

    expect(process.env.FOO).toBe("from-cwd");
    expect(process.env.BAR).toBe("1");

    process.chdir(prevCwd);
    for (const key of Object.keys(process.env)) {
      if (!(key in prevEnv)) {
        delete process.env[key];
      }
    }
    for (const [key, value] of Object.entries(prevEnv)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  });

  it("does not override an already-set env var from the shell", async () => {
    const prevEnv = { ...process.env };
    const prevCwd = process.cwd();

    const base = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-dotenv-test-"));
    const cwdDir = path.join(base, "cwd");
    const stateDir = path.join(base, "state");

    process.env.OPENCLAW_STATE_DIR = stateDir;
    process.env.FOO = "from-shell";

    await writeEnvFile(path.join(stateDir, ".env"), "FOO=from-global\n");
    await writeEnvFile(path.join(cwdDir, ".env"), "FOO=from-cwd\n");

    process.chdir(cwdDir);

    loadDotEnv({ quiet: true });

    expect(process.env.FOO).toBe("from-shell");

    process.chdir(prevCwd);
    for (const key of Object.keys(process.env)) {
      if (!(key in prevEnv)) {
        delete process.env[key];
      }
    }
    for (const [key, value] of Object.entries(prevEnv)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  });

  it("throws when the global .env exists but is not readable", async () => {
    const prevEnv = { ...process.env };
    const prevCwd = process.cwd();

    const base = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-dotenv-test-"));
    const cwdDir = path.join(base, "cwd");
    const stateDir = path.join(base, "state");
    const globalEnvPath = path.join(stateDir, ".env");

    process.env.OPENCLAW_STATE_DIR = stateDir;

    await fs.mkdir(cwdDir, { recursive: true });
    await writeEnvFile(globalEnvPath, "TELEGRAM_ON=1\n");
    const accessSpy = vi.spyOn(fsSync, "accessSync").mockImplementation((targetPath, mode) => {
      if (targetPath === globalEnvPath && mode === fsSync.constants.R_OK) {
        const err = new Error("EACCES: permission denied");
        (err as NodeJS.ErrnoException).code = "EACCES";
        throw err;
      }
    });

    process.chdir(cwdDir);

    try {
      expect(() => loadDotEnv({ quiet: true })).toThrow(/global \.env exists but is not readable/i);
    } finally {
      accessSpy.mockRestore();
      process.chdir(prevCwd);
      for (const key of Object.keys(process.env)) {
        if (!(key in prevEnv)) {
          delete process.env[key];
        }
      }
      for (const [key, value] of Object.entries(prevEnv)) {
        if (value === undefined) {
          delete process.env[key];
        } else {
          process.env[key] = value;
        }
      }
    }
  });
});
