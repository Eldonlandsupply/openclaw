export type ActionPayload = Record<string, unknown>;

export type PolicyDecision = {
  shouldProceed: boolean;
  riskScore: number;
  requiredPermissions?: string[];
  notes?: string;
};

export class PolicyEngine {
  constructor(private readonly defaultThreshold = 0.5) {}

  assess(action: string, payload: ActionPayload): PolicyDecision {
    const riskInput = payload.risk;
    const riskScore = typeof riskInput === "number" ? riskInput : this.defaultThreshold;
    const shouldProceed = riskScore <= this.defaultThreshold;
    return {
      shouldProceed,
      riskScore,
      requiredPermissions: ["WRITE", "APPROVE"],
      notes: shouldProceed ? `approved-by-policy:${action}` : `blocked-by-policy:${action}`,
    };
  }
}
