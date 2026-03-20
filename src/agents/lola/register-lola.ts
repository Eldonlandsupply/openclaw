export type LolaDashboardSurface =
  | "drafts"
  | "approvalQueue"
  | "memoryUpdates"
  | "openLoops"
  | "externalActions";

export type LolaDashboardRegistration = {
  id: "LOLA";
  name: string;
  enabled: boolean;
  readOnly: boolean;
  approvalRequired: boolean;
  writeSurfaces: string[];
  surfaces: LolaDashboardSurface[];
  panels: string[];
  approvalQueueEnabled: boolean;
  features: string[];
};

export function registerLola(params?: { writeEnabled?: boolean }): LolaDashboardRegistration {
  const writeEnabled = params?.writeEnabled ?? false;
  return {
    id: "LOLA",
    name: "LOLA",
    enabled: true,
    readOnly: false,
    approvalRequired: true,
    writeSurfaces: ["drafts", "memory", "open_loops", "external_actions"],
    surfaces: ["drafts", "approvalQueue", "memoryUpdates", "openLoops", "externalActions"],
    panels: [
      "Drafts awaiting approval",
      "Approval queue",
      "Memory updates",
      "Open loops",
      "External actions",
      "Audit log",
    ],
    approvalQueueEnabled: true,
    features: [
      "drafts",
      "memory-updates",
      "open-loops",
      "approvals",
      ...(writeEnabled ? ["external-actions"] : []),
    ],
  };
}
