import { describe, expect, test } from "vitest";
import { scoreCommit, type UpstreamWatchConfig } from "./upstream-watch.ts";

const config: UpstreamWatchConfig = {
  upstreamRepo: "openclaw/openclaw",
  upstreamRemoteName: "upstream-watch",
  defaultBaseBranch: "main",
  stateIssueTitle: "Upstream watch state",
  reportOutputDir: ".artifacts/upstream-watch",
  reportTemplatePath: ".github/upstream-watch/report-template.md",
  labels: {
    "upstream-sync": "upstream-sync",
    "safe-port": "safe-port",
    "needs-review": "needs-review",
    "breaking-risk": "breaking-risk",
    "rejected-by-policy": "rejected-by-policy",
  },
  classification: {
    categoryKeywords: {
      security: ["security", "token"],
      "bug fix": ["fix", "regression"],
      reliability: ["retry", "guardrail"],
      performance: ["performance", "cache"],
      "cost efficiency": ["cost", "reduce"],
      "developer experience": ["docs", "lint", "test"],
      "UI/dashboard": ["ui", "dashboard"],
      "breaking change": ["breaking", "remove"],
      "opinionated/nonessential": ["cleanup", "copy"],
    },
    fitWeights: {
      security: 7,
      "bug fix": 5,
      reliability: 5,
      performance: 4,
      "cost efficiency": 4,
      "developer experience": 1,
      "UI/dashboard": 1,
      "breaking change": -8,
      "opinionated/nonessential": -4,
    },
    strongFitThreshold: 6,
    possibleFitThreshold: 2,
    maxSafeFiles: 8,
    maxSafeInsertions: 220,
    maxSafeDeletions: 140,
    riskyFileThreshold: 20,
  },
  policy: {
    rejectPathPrefixes: ["src/agents/"],
    manualReviewPathPrefixes: ["ui/", ".github/workflows/"],
    preferPathPrefixes: ["src/infra/", "src/commands/", "scripts/"],
    rejectSubjectKeywords: ["breaking", "remove"],
    riskySubjectKeywords: ["refactor", "workflow", "ui"],
    forceSafeSubjectKeywords: ["fix", "security", "regression"],
  },
};

describe("scoreCommit", () => {
  test("marks small security fixes as safe strong fit", () => {
    const scored = scoreCommit(config, {
      sha: "a".repeat(40),
      shortSha: "aaaaaaa",
      subject: "fix security token guardrail",
      body: "prevent regression in auth path",
      changedFiles: ["src/infra/session.ts"],
      insertions: 32,
      deletions: 7,
    });

    expect(scored.fit).toBe("strong fit");
    expect(scored.lane).toBe("safe");
    expect(scored.categories).toContain("security");
  });

  test("rejects breaking or fork-owned changes", () => {
    const scored = scoreCommit(config, {
      sha: "b".repeat(40),
      shortSha: "bbbbbbb",
      subject: "breaking remove agent runtime",
      body: "",
      changedFiles: ["src/agents/runtime.ts"],
      insertions: 20,
      deletions: 40,
    });

    expect(scored.fit).toBe("reject");
    expect(scored.lane).toBe("reject");
  });

  test("rejects UI churn by default", () => {
    const scored = scoreCommit(config, {
      sha: "c".repeat(40),
      shortSha: "ccccccc",
      subject: "ui dashboard cleanup",
      body: "",
      changedFiles: ["ui/dashboard.ts"],
      insertions: 40,
      deletions: 10,
    });

    expect(scored.fit).toBe("reject");
    expect(scored.lane).toBe("reject");
  });
});
