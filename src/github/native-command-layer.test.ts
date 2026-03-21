import { describe, expect, it } from "vitest";
import {
  buildGitHubActionPlan,
  createGitHubAuditEntry,
  discoverGhCommandCatalog,
} from "./native-command-layer.js";

describe("discoverGhCommandCatalog", () => {
  it("parses command families from gh help output", async () => {
    const mockExec = async (_file: string, args: string[]) => {
      if (args[0] === "--help") {
        return {
          stdout: `GitHub CLI 2.68.1\n\nCORE COMMANDS\n  auth        Authenticate gh and git\n  pr          Manage pull requests\n  repo        Manage repositories\n`,
          stderr: "",
        };
      }
      return {
        stdout: `REFERENCE\n  issue       Manage issues\n  workflow    View details about GitHub Actions workflows\n  release     Manage releases\n`,
        stderr: "",
      };
    };

    await expect(discoverGhCommandCatalog({ exec: mockExec as never })).resolves.toEqual({
      version: "2.68.1",
      families: ["auth", "pr", "repo", "issue", "workflow", "release"],
    });
  });
});

describe("buildGitHubActionPlan", () => {
  it("builds a medium-risk draft PR plan", () => {
    const plan = buildGitHubActionPlan(
      {
        requestId: "req-1",
        sourceAgent: "lola",
        userIdentity: "operator-1",
        targetScope: {
          owner: "openclaw",
          repo: "openclaw",
          branch: "feature-x",
          baseBranch: "main",
        },
        naturalLanguageRequest: "Create a draft PR from this branch into main",
        requestingChannel: "openclaw",
        preApproved: false,
        approvalPolicy: {
          allowAutoApproveWrites: true,
          allowAutoApproveHighRisk: false,
          allowMessagingWrites: false,
        },
      },
      { families: ["pr", "repo"], version: "2.68.1" },
    );

    expect(plan).toMatchObject({
      intent: "write",
      commandFamily: "pr",
      riskLevel: "medium",
      approvalRequired: false,
      executionStatus: "approved",
      ghCommandPlan: [
        'gh pr create --repo openclaw/openclaw --base main --head feature-x --draft --title "TITLE" --body-file BODY.md',
      ],
    });
  });

  it("blocks critical secret mutation from a messaging channel", () => {
    const plan = buildGitHubActionPlan({
      requestId: "req-2",
      sourceAgent: "whatsapp",
      userIdentity: "operator-2",
      targetScope: {
        owner: "openclaw",
        repo: "openclaw",
      },
      naturalLanguageRequest: "Set a repo secret named PROD_TOKEN",
      requestingChannel: "whatsapp",
      preApproved: false,
      approvalPolicy: {
        allowAutoApproveWrites: false,
        allowAutoApproveHighRisk: false,
        allowMessagingWrites: false,
      },
    });

    expect(plan).toMatchObject({
      intent: "admin",
      commandFamily: "secret",
      riskLevel: "critical",
      approvalRequired: true,
      executionStatus: "blocked",
    });
    expect(plan.ghCommandPlan[0]).toContain("gh secret set NAME --repo openclaw/openclaw");
  });

  it("maps failed workflow inspection to a low-risk read plan", () => {
    const plan = buildGitHubActionPlan({
      requestId: "req-3",
      sourceAgent: "openclaw",
      userIdentity: "operator-3",
      targetScope: {
        owner: "openclaw",
        repo: "openclaw",
      },
      naturalLanguageRequest: "Show me failed workflow runs today",
      requestingChannel: "openclaw",
      preApproved: false,
      approvalPolicy: {
        allowAutoApproveWrites: false,
        allowAutoApproveHighRisk: false,
        allowMessagingWrites: false,
      },
    });

    expect(plan).toMatchObject({
      intent: "read",
      commandFamily: "workflow",
      riskLevel: "low",
      approvalRequired: false,
      executionStatus: "approved",
      ghCommandPlan: ["gh run list --repo openclaw/openclaw --status failure --limit 20"],
    });
  });
});

describe("createGitHubAuditEntry", () => {
  it("records executed command metadata", () => {
    const plan = buildGitHubActionPlan({
      requestId: "req-4",
      sourceAgent: "future_agent",
      userIdentity: "operator-4",
      targetScope: {
        owner: "openclaw",
        repo: "openclaw",
      },
      naturalLanguageRequest: "Comment on issue 142 with this note",
      requestingChannel: "slack",
      preApproved: true,
      approvalPolicy: {
        allowAutoApproveWrites: true,
        allowAutoApproveHighRisk: false,
        allowMessagingWrites: true,
      },
    });

    const audit = createGitHubAuditEntry({
      plan,
      requestingChannel: "slack",
      executedCommands: plan.ghCommandPlan,
      stdoutSummary: "comment posted",
      stderrSummary: "",
      result: "success",
      approvalSource: "repo-policy:auto",
      timestamp: "2026-03-21T00:00:00.000Z",
    });

    expect(audit).toMatchObject({
      requestingChannel: "slack",
      resolvedActor: "operator-4",
      repoScope: "openclaw/openclaw",
      riskLevel: "medium",
      result: "success",
    });
  });
});
