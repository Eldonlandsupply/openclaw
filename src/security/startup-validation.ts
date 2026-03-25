import path from "node:path";
import { resolveStateDir } from "../config/paths.js";
import {
  resolveAuthorizedNumbersConfig,
  validateAuthorizedNumbersConfig,
} from "./authorized-numbers.js";

function parseTruthy(value: string | undefined): boolean {
  const normalized = value?.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}

function firstNonEmpty(...values: Array<string | undefined>): string | undefined {
  for (const value of values) {
    const trimmed = value?.trim();
    if (trimmed) {
      return trimmed;
    }
  }
  return undefined;
}

function isGraphConfigured(env: NodeJS.ProcessEnv): boolean {
  return Boolean(
    env.M365_TENANT_ID ||
    env.M365_CLIENT_ID ||
    env.M365_CLIENT_SECRET ||
    env.M365_USER_EMAIL ||
    env.LOLA_M365_TENANT_ID ||
    env.LOLA_M365_CLIENT_ID ||
    env.LOLA_M365_CLIENT_SECRET ||
    env.LOLA_M365_MAILBOX_UPN,
  );
}

export function resolveM365TokenCachePath(env: NodeJS.ProcessEnv = process.env): string {
  const configured = env.M365_TOKEN_CACHE_FILE?.trim();
  if (configured) {
    return configured;
  }
  return path.join(resolveStateDir(env), "credentials", "m365", "token-cache.enc.json");
}

export function validateSecurityStartupEnv(env: NodeJS.ProcessEnv = process.env): void {
  const errors: string[] = [];

  for (const message of validateAuthorizedNumbersConfig(env)) {
    errors.push(message);
  }

  const authCfg = resolveAuthorizedNumbersConfig(env);
  if (authCfg.enabled && authCfg.entries.length === 0) {
    errors.push(
      "Strict WhatsApp command authorization is enabled, but no authorized numbers were parsed.",
    );
  }

  const graphEnabled =
    parseTruthy(env.LOLA_ENABLED) &&
    (parseTruthy(env.LOLA_EXTERNAL_ACTIONS_ENABLED) || isGraphConfigured(env));
  if (graphEnabled) {
    const tenantId = firstNonEmpty(
      env.M365_TENANT_ID,
      env.LOLA_M365_TENANT_ID,
      env.MSTEAMS_TENANT_ID,
    );
    const clientId = firstNonEmpty(env.M365_CLIENT_ID, env.LOLA_M365_CLIENT_ID);
    const clientSecret = firstNonEmpty(env.M365_CLIENT_SECRET, env.LOLA_M365_CLIENT_SECRET);
    const mailbox = firstNonEmpty(env.M365_USER_EMAIL, env.LOLA_M365_MAILBOX_UPN);

    if (!tenantId) {
      errors.push(
        "Microsoft Graph is enabled but tenant ID is missing (set M365_TENANT_ID or LOLA_M365_TENANT_ID).",
      );
    }
    if (!clientId) {
      errors.push(
        "Microsoft Graph is enabled but client ID is missing (set M365_CLIENT_ID or LOLA_M365_CLIENT_ID).",
      );
    }
    if (!clientSecret) {
      errors.push(
        "Microsoft Graph is enabled but client secret is missing (set M365_CLIENT_SECRET or LOLA_M365_CLIENT_SECRET).",
      );
    }
    if (!mailbox) {
      errors.push(
        "Microsoft Graph is enabled but mailbox user is missing (set M365_USER_EMAIL or LOLA_M365_MAILBOX_UPN).",
      );
    }

    const tokenCachePath = resolveM365TokenCachePath(env);
    if (!tokenCachePath.endsWith(".enc.json")) {
      errors.push(
        "M365_TOKEN_CACHE_FILE must end with .enc.json so token cache is encrypted at rest.",
      );
    }
  }

  if (errors.length > 0) {
    throw new Error(`Security startup validation failed:\n- ${errors.join("\n- ")}`);
  }
}
