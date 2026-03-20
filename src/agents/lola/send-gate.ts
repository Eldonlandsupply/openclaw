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
  }

  block() {
    return true;
  }
}
