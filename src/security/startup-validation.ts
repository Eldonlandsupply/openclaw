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

function validateLolaTelegramConfig(env: NodeJS.ProcessEnv, errors: string[]) {
  const enabled = parseTruthy(env.LOLA_TELEGRAM_ENABLED);
  if (!enabled) {
    return;
  }
  const token = env.TELEGRAM_BOT_TOKEN?.trim();
  const mode = (env.TELEGRAM_MODE ?? "polling").trim().toLowerCase();
  const allowedUsers = env.TELEGRAM_ALLOWED_USER_IDS?.trim();
  if (!token) {
    errors.push("LOLA Telegram bridge is enabled but TELEGRAM_BOT_TOKEN is missing.");
  }
  if (!allowedUsers) {
    errors.push(
      "LOLA Telegram bridge is enabled but TELEGRAM_ALLOWED_USER_IDS is missing. Add at least one Telegram user ID.",
    );
  }
  if (mode === "webhook") {
    if (!env.TELEGRAM_WEBHOOK_URL?.trim()) {
      errors.push("TELEGRAM_MODE=webhook requires TELEGRAM_WEBHOOK_URL.");
    }
    if (!env.TELEGRAM_WEBHOOK_SECRET?.trim()) {
      errors.push("TELEGRAM_MODE=webhook requires TELEGRAM_WEBHOOK_SECRET.");
    }
  }
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
  validateLolaTelegramConfig(env, errors);

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
