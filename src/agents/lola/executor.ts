import { LolaActionLogger } from "./action-logger.js";
import { ApprovalEngine } from "./approval-engine.js";
import { saveExternalAction } from "./memory-store.js";
import { PolicyEngine } from "./policy-engine.js";
import { OutlookActionProvider, type OutlookSendDraftPayload } from "./providers/outlook-action.js";

export type ExecutorConfig = {
  workspaceDir: string;
  dryRun: boolean;
  provider?: OutlookActionProvider;
};

export class Executor {
  readonly #logger: LolaActionLogger;
  readonly #provider: OutlookActionProvider;

  constructor(
    private readonly policy: PolicyEngine,
    private readonly approvals: ApprovalEngine,
    private readonly config: ExecutorConfig,
  ) {
    this.#logger = new LolaActionLogger(config.workspaceDir);
    this.#provider = config.provider ?? new OutlookActionProvider();
  }

  async execute(
    actionId: string,
    payload: OutlookSendDraftPayload & { risk?: number },
    dryRun: boolean,
  ) {
    const decision = this.policy.assess(actionId, payload);
    if (!decision.shouldProceed) {
      await this.#logger.log({
        event: "external_action_blocked",
        agent: "lola-executor",
        targetType: "draft",
        targetId: payload.draftId,
        status: "blocked",
        summary: "Blocked external action by policy",
        details: { actionId, payload, decision },
        redactionApplied: false,
      });
      return { ok: false as const, reason: "blocked-by-policy", decision };
    }

    const result = await this.#provider.sendDraft(payload, dryRun);
    await saveExternalAction(this.config.workspaceDir, {
      id: actionId,
      actionType: "send_draft",
      provider: result.provider,
      payloadSummary: payload.subject,
      payloadRef: payload.draftId,
      reason: decision.notes,
      status: dryRun ? "dry_run" : "executed",
      createdAt: new Date().toISOString(),
    });
    await this.#logger.log({
      event: "external_action_executed",
      agent: "lola-executor",
      targetType: "draft",
      targetId: payload.draftId,
      status: dryRun ? "dry_run" : "executed",
      summary: "Executed external action",
      details: { actionId, provider: result.provider, decision },
      redactionApplied: false,
    });
    return {
      ok: true as const,
      executed: !dryRun,
      dryRun,
      actionId,
      payload,
      externalRef: result.externalRef,
      decision,
      approvalsConfigured: typeof this.approvals === "object",
    };
  }
}
