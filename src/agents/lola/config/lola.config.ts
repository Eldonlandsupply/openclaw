export type LolaWriteConfig = {
  writeEnabled: boolean;
  toggles: {
    inbox: boolean;
    memory: boolean;
    calendar: boolean;
    briefing: boolean;
    followthrough: boolean;
    audit: boolean;
  };
};

export const LOLA_WRITE_CONFIG_DEFAULTS: LolaWriteConfig = {
  writeEnabled: false,
  toggles: {
    inbox: true,
    memory: true,
    calendar: true,
    briefing: true,
    followthrough: true,
    audit: true,
  },
};

export const LOLA_CONFIG_DEFAULTS = {
  enabled: true,
  dryRun: true,
  approvalMode: "required",
  executiveName: "Executive Placeholder",
  timezone: "America/New_York",
  readAdapters: ["outlook"] as const,
  memoryEnabled: true,
  ...LOLA_WRITE_CONFIG_DEFAULTS,
};
