import type { ApprovalQueueItem } from "./schemas/approval-queue.js";
import {
  LOLA_WRITE_TOGGLES_DEFAULTS,
  type LolaSubagentKey,
  type LolaWriteToggles,
} from "./config/lola.config.js";

export type SendGateOptions = {
  allowExternalActions?: boolean;
  writeEnabled?: boolean;
  dryRun?: boolean;
  approvalMode?: "required" | "optional";
  writeToggles?: Partial<LolaWriteToggles>;
};

export class SendGate {
  readonly #allowExternalActions: boolean;
  readonly #writeEnabled: boolean;
  readonly #dryRun: boolean;
  readonly #approvalMode: "required" | "optional";
  readonly #writeToggles: LolaWriteToggles;

  constructor(options: SendGateOptions = {}) {
    this.#allowExternalActions = options.allowExternalActions ?? false;
    this.#writeEnabled = options.writeEnabled ?? false;
    this.#dryRun = options.dryRun ?? true;
    this.#approvalMode = options.approvalMode ?? "required";
    this.#writeToggles = {
      ...LOLA_WRITE_TOGGLES_DEFAULTS,
      ...options.writeToggles,
    };
  }

  approve(approval?: ApprovalQueueItem) {
    if (!approval) {
      return this.#allowExternalActions && !this.#dryRun;
    }
    return this.canExecuteExternalAction(approval);
  }

  block() {
    return !this.approve();
  }

  reject(approval?: ApprovalQueueItem) {
    return approval ? { ...approval, status: "rejected" as const } : false;
  }

  canExecuteExternalAction(approval: ApprovalQueueItem) {
    if (!this.#writeEnabled || this.#dryRun || !this.#allowExternalActions) {
      return false;
    }
    if (this.#approvalMode === "required" && approval.status !== "approved") {
      return false;
    }
    return true;
  }

  canQueueInternalWrite(agent: LolaSubagentKey) {
    return this.#writeEnabled && this.#writeToggles[agent];
  }

  requiresApproval(agent?: LolaSubagentKey) {
    if (!agent) {
      return this.#approvalMode !== "optional";
    }
    return this.#approvalMode !== "optional" && this.canQueueInternalWrite(agent);
  }
}
