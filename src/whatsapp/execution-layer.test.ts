import { describe, expect, it } from "vitest";
import {
  approvalRequiredForRepoRisk,
  defaultExecutionTierForIntent,
  repoChangeShouldOpenPr,
  WhatsAppActionSchema,
} from "./execution-layer.js";

describe("whatsapp execution layer schema", () => {
  it("accepts a structured action object", () => {
    const parsed = WhatsAppActionSchema.parse({
      messageId: "wamid-1",
      userId: "+15551234567",
      channel: "whatsapp",
      rawText: "Fix the CI failure and open a PR",
      normalizedText: "fix the ci failure and open a pr",
      intentType: "bug_fix_request",
      confidence: 0.94,
      executionTier: "tier_3_approval",
      repoRiskTier: "tier_c_moderate",
      approvalRequired: true,
      requestedAction: "Fix the failing CI workflow in openclaw/openclaw.",
      successDefinition: "A branch is created, checks pass locally, and a PR is ready.",
    });

    expect(parsed.status).toBe("queued");
    expect(parsed.toolRoute).toEqual([]);
  });

  it("maps intents to the expected execution tier", () => {
    expect(defaultExecutionTierForIntent("task_creation")).toBe("tier_2_auto_execute");
    expect(defaultExecutionTierForIntent("repository_update_request")).toBe("tier_3_approval");
    expect(defaultExecutionTierForIntent("unsafe_blocked")).toBe("tier_4_blocked");
  });

  it("enforces approval and PR defaults for repo risk", () => {
    expect(approvalRequiredForRepoRisk("tier_b_low")).toBe(false);
    expect(approvalRequiredForRepoRisk("tier_c_moderate")).toBe(true);
    expect(repoChangeShouldOpenPr("tier_a_read")).toBe(false);
    expect(repoChangeShouldOpenPr("tier_d_high")).toBe(true);
  });
});
