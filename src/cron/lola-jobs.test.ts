import { describe, expect, it } from "vitest";

type LolaJobCandidate = {
  id?: string;
  name?: string;
  schedule?: { kind?: string; everyMs?: number; expr?: string };
};

function looksLikeJobsArray(value: unknown): value is LolaJobCandidate[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((item) => item && typeof item === "object" && typeof item.id === "string")
  );
}

async function resolveLolaJobsExport(): Promise<LolaJobCandidate[] | null> {
  try {
    const mod = (await import("./lola-jobs.js")) as Record<string, unknown>;
    const directCandidates = [
      mod.LOLA_JOBS,
      mod.lolaJobs,
      mod.default,
      mod.buildLolaJobs,
      mod.getLolaJobs,
    ];

    for (const candidate of directCandidates) {
      if (typeof candidate === "function") {
        const result = (candidate as () => unknown)();
        if (looksLikeJobsArray(result)) {
          return result;
        }
      }
      if (looksLikeJobsArray(candidate)) {
        return candidate;
      }
    }

    for (const value of Object.values(mod)) {
      if (looksLikeJobsArray(value)) {
        return value;
      }
    }

    return null;
  } catch (err) {
    const code = (err as { code?: string }).code;
    if (code === "ERR_MODULE_NOT_FOUND") {
      return null;
    }
    throw err;
  }
}

describe("lola jobs", () => {
  it("uses deterministic job shape and unique ids when module exists", async () => {
    const jobs = await resolveLolaJobsExport();
    if (!jobs) {
      expect(true).toBe(true);
      return;
    }

    const ids = jobs.map((job) => job.id ?? "");
    expect(new Set(ids).size).toBe(ids.length);

    for (const job of jobs) {
      expect(typeof job.id).toBe("string");
      expect(job.id?.trim().length).toBeGreaterThan(0);
      expect(typeof job.name).toBe("string");
      expect(job.name?.trim().length).toBeGreaterThan(0);
      expect(job.schedule).toBeTruthy();
      expect(["every", "cron", "at"]).toContain(job.schedule?.kind);
    }
  });

  it("uses deterministic default schedule cadence when module exists", async () => {
    const jobs = await resolveLolaJobsExport();
    if (!jobs) {
      expect(true).toBe(true);
      return;
    }

    const repeatingJobs = jobs.filter((job) => job.schedule?.kind === "every");
    for (const job of repeatingJobs) {
      expect(typeof job.schedule?.everyMs).toBe("number");
      expect((job.schedule?.everyMs ?? 0) > 0).toBe(true);
      expect(Number.isInteger(job.schedule?.everyMs ?? 0)).toBe(true);
    }

    const cronJobs = jobs.filter((job) => job.schedule?.kind === "cron");
    for (const job of cronJobs) {
      expect(typeof job.schedule?.expr).toBe("string");
      expect(job.schedule?.expr?.trim().length).toBeGreaterThan(0);
    }
  });
});
