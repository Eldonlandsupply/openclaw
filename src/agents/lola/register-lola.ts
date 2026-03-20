export type LolaDashboardRegistration = {
  id: "LOLA";
  name: string;
  enabled: boolean;
  readOnly: boolean;
};

export function registerLola(): LolaDashboardRegistration {
  return {
    id: "LOLA",
    name: "LOLA",
    enabled: true,
    readOnly: true,
  };
}
