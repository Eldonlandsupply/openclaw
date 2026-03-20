export type LolaDashboardRegistration = {
  id: "LOLA";
  name: string;
  enabled: boolean;
  readOnly: boolean;
  surfaces: Array<"drafts" | "approvalQueue" | "memoryUpdates" | "openLoops">;
};

export function registerLola(params?: { writeEnabled?: boolean }): LolaDashboardRegistration {
  return {
    id: "LOLA",
    name: "LOLA",
    enabled: true,
    readOnly: !(params?.writeEnabled ?? false),
    surfaces: ["drafts", "approvalQueue", "memoryUpdates", "openLoops"],
  };
}
