export type LolaDashboardRegistration = {
  id: "LOLA";
  name: string;
  enabled: boolean;
  readOnly: boolean;
  approvalRequired: boolean;
  writeSurfaces: string[];
  surfaces: Array<"drafts" | "approvalQueue" | "memoryUpdates" | "openLoops">;
  panels: string[];
  approvalQueueEnabled: boolean;
};

export function registerLola(params?: { writeEnabled?: boolean }): LolaDashboardRegistration {
  return {
    id: "LOLA",
    name: "LOLA",
    enabled: true,
    readOnly: false,
    approvalRequired: true,
    writeSurfaces: ["drafts", "memory", "open_loops"],
    readOnly: !(params?.writeEnabled ?? false),
    surfaces: ["drafts", "approvalQueue", "memoryUpdates", "openLoops"],
    readOnly: false,
    panels: [
      "Drafts awaiting approval",
      "Approval queue",
      "Memory updates",
      "Open loops",
      "Audit log",
    ],
    approvalQueueEnabled: true,
  };
}
