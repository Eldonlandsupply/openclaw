export type LolaDashboardRegistration = {
  id: "LOLA";
  name: string;
  enabled: boolean;
  readOnly: boolean;
  approvalRequired: boolean;
  writeSurfaces: string[];
};

export function registerLola(): LolaDashboardRegistration {
  return {
    id: "LOLA",
    name: "LOLA",
    enabled: true,
    readOnly: false,
    approvalRequired: true,
    writeSurfaces: ["drafts", "memory", "open_loops"],
  };
}
