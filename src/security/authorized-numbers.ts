import { normalizeE164 } from "../utils.js";

export type AuthorizedNumberRole = "ceo" | "assistant" | "allowlist";

export type AuthorizedNumberEntry = {
  number: string;
  role: AuthorizedNumberRole;
  label?: string;
  source:
    | "WHATSAPP_CEO_PRIMARY_NUMBER"
    | "WHATSAPP_AUTHORIZED_ASSISTANTS"
    | "WHATSAPP_ALLOWED_NUMBERS";
};

export type AuthorizedNumbersConfig = {
  enabled: boolean;
  entries: AuthorizedNumberEntry[];
};

export type AuthorizedNumberMatch = {
  authorized: boolean;
  entry?: AuthorizedNumberEntry;
  normalizedSender?: string;
  reason?: string;
};

function parseTruthy(value: string | undefined): boolean {
  const normalized = value?.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}

function parseList(raw: string | undefined): string[] {
  if (!raw) {
    return [];
  }
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseNumberWithOptionalLabel(raw: string): { number: string; label?: string } {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { number: "" };
  }
  const [left, right] = trimmed.split("|").map((item) => item?.trim());
  if (!right) {
    return { number: left ?? "" };
  }

  if (left?.startsWith("+")) {
    return { number: left, label: right };
  }
  if (right.startsWith("+")) {
    return { number: right, label: left };
  }
  return { number: left ?? "", label: right };
}

function normalizeNumber(input: string): string {
  const normalized = normalizeE164(input);
  const digits = normalized.replace(/\D/g, "");
  if (!digits) {
    throw new Error(`invalid phone number: ${input}`);
  }
  return normalized;
}

export function isWhatsAppStrictAuthorizationRequired(
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  if (parseTruthy(env.LOLA_ENABLED)) {
    return true;
  }
  return Boolean(
    env.WHATSAPP_CEO_PRIMARY_NUMBER ||
    env.WHATSAPP_ALLOWED_NUMBERS ||
    env.WHATSAPP_AUTHORIZED_ASSISTANTS,
  );
}

export function resolveAuthorizedNumbersConfig(
  env: NodeJS.ProcessEnv = process.env,
): AuthorizedNumbersConfig {
  const enabled = isWhatsAppStrictAuthorizationRequired(env);
  if (!enabled) {
    return { enabled: false, entries: [] };
  }

  const entries: AuthorizedNumberEntry[] = [];
  const ceoRaw = (env.WHATSAPP_CEO_PRIMARY_NUMBER ?? "").trim();
  if (ceoRaw) {
    const parsed = parseNumberWithOptionalLabel(ceoRaw);
    entries.push({
      number: normalizeNumber(parsed.number),
      role: "ceo",
      label: parsed.label,
      source: "WHATSAPP_CEO_PRIMARY_NUMBER",
    });
  }

  for (const raw of parseList(env.WHATSAPP_AUTHORIZED_ASSISTANTS)) {
    const parsed = parseNumberWithOptionalLabel(raw);
    entries.push({
      number: normalizeNumber(parsed.number),
      role: "assistant",
      label: parsed.label,
      source: "WHATSAPP_AUTHORIZED_ASSISTANTS",
    });
  }

  for (const raw of parseList(env.WHATSAPP_ALLOWED_NUMBERS)) {
    const parsed = parseNumberWithOptionalLabel(raw);
    entries.push({
      number: normalizeNumber(parsed.number),
      role: "allowlist",
      label: parsed.label,
      source: "WHATSAPP_ALLOWED_NUMBERS",
    });
  }

  const deduped: AuthorizedNumberEntry[] = [];
  for (const entry of entries) {
    if (deduped.some((existing) => existing.number === entry.number)) {
      continue;
    }
    deduped.push(entry);
  }

  return { enabled: true, entries: deduped };
}

export function validateAuthorizedNumbersConfig(env: NodeJS.ProcessEnv = process.env): string[] {
  const cfg = resolveAuthorizedNumbersConfig(env);
  if (!cfg.enabled) {
    return [];
  }
  const errors: string[] = [];
  if (!cfg.entries.some((entry) => entry.role === "ceo")) {
    errors.push(
      "WHATSAPP_CEO_PRIMARY_NUMBER is required when strict WhatsApp authorization is enabled.",
    );
  }
  if (cfg.entries.length === 0) {
    errors.push(
      "At least one authorized number is required. Configure WHATSAPP_CEO_PRIMARY_NUMBER and optional assistants.",
    );
  }
  return errors;
}

export function isAuthorizedWhatsAppCommandSender(params: {
  senderCandidates: string[];
  env?: NodeJS.ProcessEnv;
}): AuthorizedNumberMatch {
  const cfg = resolveAuthorizedNumbersConfig(params.env);
  if (!cfg.enabled) {
    return { authorized: true };
  }
  if (cfg.entries.length === 0) {
    return {
      authorized: false,
      reason: "authorized number list is empty",
    };
  }

  const normalizedCandidates = params.senderCandidates
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      try {
        return normalizeNumber(entry);
      } catch {
        return undefined;
      }
    })
    .filter((entry): entry is string => Boolean(entry));

  for (const candidate of normalizedCandidates) {
    const entry = cfg.entries.find((item) => item.number === candidate);
    if (entry) {
      return { authorized: true, entry, normalizedSender: candidate };
    }
  }

  return {
    authorized: false,
    normalizedSender: normalizedCandidates[0],
    reason: "sender is not in WHATSAPP allowed list",
  };
}
