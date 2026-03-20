import { LOLA_DEFAULTS } from "./config/lola.defaults.js";
import { registerLola } from "./register-lola.js";

export type LolaFirstBootState = {
  config: typeof LOLA_DEFAULTS;
  dashboard: ReturnType<typeof registerLola>;
  externalEffectsBlocked: true;
};

export function initializeLolaPhaseOne(): LolaFirstBootState {
  return {
    config: LOLA_DEFAULTS,
    dashboard: registerLola({ writeEnabled: LOLA_DEFAULTS.writeEnabled }),
    externalEffectsBlocked: true,
  };
}
