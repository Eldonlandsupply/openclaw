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
export const LOLA_SUBAGENT_KEYS = [
  "inbox",
  "memory",
  "calendar",
  "briefing",
  "followthrough",
  "audit",
] as const;

export type LolaSubagentKey = (typeof LOLA_SUBAGENT_KEYS)[number];

export type LolaWriteToggles = Record<LolaSubagentKey, boolean>;

export const LOLA_WRITE_TOGGLES_DEFAULTS: LolaWriteToggles = {
  inbox: false,
  memory: false,
  calendar: false,
  briefing: false,
  followthrough: false,
  audit: false,
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
  writeEnabled: false,
  writeToggles: LOLA_WRITE_TOGGLES_DEFAULTS,
};
