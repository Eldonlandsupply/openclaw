import {
  LOLA_WRITE_TOGGLES_DEFAULTS,
  type LolaSubagentKey,
  type LolaWriteToggles,
} from "./config/lola.config.js";

export type SendGateOptions = {
  allowExternalActions?: boolean;
  writeEnabled?: boolean;
  writeToggles?: Partial<LolaWriteToggles>;
};

export class SendGate {
  readonly #allowExternalActions: boolean;
  readonly #writeEnabled: boolean;
  readonly #writeToggles: LolaWriteToggles;

  constructor(options: SendGateOptions = {}) {
    this.#allowExternalActions = options.allowExternalActions ?? false;
    this.#writeEnabled = options.writeEnabled ?? false;
    this.#writeToggles = {
      ...LOLA_WRITE_TOGGLES_DEFAULTS,
      ...options.writeToggles,
    };
  }

  approve() {
    return this.#allowExternalActions;
  }

  block() {
    return !this.#allowExternalActions;
  }

  canQueueInternalWrite(agent: LolaSubagentKey) {
    return this.#writeEnabled && this.#writeToggles[agent];
  }

  requiresApproval(agent: LolaSubagentKey) {
    return this.canQueueInternalWrite(agent);
  }
}
