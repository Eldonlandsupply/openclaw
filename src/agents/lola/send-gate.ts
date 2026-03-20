import type { LolaWriteConfig } from "./config/lola.config.js";
import type { ApprovalQueueItem } from "./schemas/approval-queue.js";

export class SendGate {
  constructor(
    private readonly config: Pick<LolaWriteConfig, "writeEnabled"> & {
      dryRun?: boolean;
      approvalMode?: "required" | "optional";
    } = {
      writeEnabled: false,
      dryRun: true,
      approvalMode: "required",
    },
  ) {}

  approve(approval?: ApprovalQueueItem) {
    if (!approval) {
      return false;
    }
    return this.canExecuteExternalAction(approval);
  }

  canExecuteExternalAction(approval: ApprovalQueueItem) {
    if (!this.config.writeEnabled) {
      return false;
    }
    if (this.config.dryRun ?? true) {
      return false;
    }
    if (this.config.approvalMode === "required" && approval.status !== "approved") {
      return false;
    }
    return true;
  }

  requiresApproval() {
    return this.config.approvalMode !== "optional";
  }

  reject(approval?: ApprovalQueueItem) {
    return approval ? { ...approval, status: "rejected" as const } : false;
import {
  LOLA_WRITE_TOGGLES_DEFAULTS,
  type LolaSubagentKey,
  type LolaWriteToggles,
} from "./config/lola.config.js";

export type SendGateOptions = {
  allowExternalActions?: boolean;
  writeEnabled?: boolean;
  writeToggles?: Partial<LolaWriteToggles>;
};

export class SendGate {
  readonly #allowExternalActions: boolean;
  readonly #writeEnabled: boolean;
  readonly #writeToggles: LolaWriteToggles;

  constructor(options: SendGateOptions = {}) {
    this.#allowExternalActions = options.allowExternalActions ?? false;
    this.#writeEnabled = options.writeEnabled ?? false;
    this.#writeToggles = {
      ...LOLA_WRITE_TOGGLES_DEFAULTS,
      ...options.writeToggles,
    };
  }

  approve() {
    return this.#allowExternalActions;
  }

  block() {
    return !this.#allowExternalActions;
  }

  canQueueInternalWrite(agent: LolaSubagentKey) {
    return this.#writeEnabled && this.#writeToggles[agent];
  }

  requiresApproval(agent: LolaSubagentKey) {
    return this.canQueueInternalWrite(agent);
  }
}
