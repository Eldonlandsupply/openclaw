export type LolaDashboardRegistration = {
  id: "LOLA";
  name: string;
  enabled: boolean;
  readOnly: boolean;
  panels: string[];
  approvalQueueEnabled: boolean;
};

export function registerLola(): LolaDashboardRegistration {
  return {
    id: "LOLA",
    name: "LOLA",
    enabled: true,
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
