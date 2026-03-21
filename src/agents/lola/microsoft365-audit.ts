export type GraphPermissionMode = "delegated" | "application" | "bot";

export type LolaGraphCapabilityId =
  | "mail.read"
  | "mail.search"
  | "mail.read.thread"
  | "mail.draft"
  | "mail.send"
  | "mail.reply"
  | "mail.move"
  | "mail.categorize"
  | "calendar.read"
  | "contacts.read"
  | "teams.chat.read"
  | "teams.chat.write"
  | "teams.channel.read"
  | "teams.channel.write"
  | "teams.meeting.read"
  | "teams.transcript.read"
  | "teams.notifications";

export type LolaCapabilityRequirement = {
  id: LolaGraphCapabilityId;
  surface: "mail" | "calendar" | "contacts" | "teams";
  description: string;
  delegated: string[];
  application: string[];
  bot?: string[];
  notes?: string;
};

export type LolaMicrosoft365Env = {
  tenantId?: string;
  clientId?: string;
  clientSecret?: string;
  mailboxUpn?: string;
  expectedUserPrincipalName?: string;
  expectedTenantId?: string;
  delegatedScopes?: string[];
  applicationRoles?: string[];
  botScopes?: string[];
  accessTokenClaims?: Record<string, unknown>;
  authModeHints: GraphPermissionMode[];
};

export type LolaAuditSeverity = "ok" | "unproven" | "missing" | "misconfigured" | "blocked";

export type LolaAuditFinding = {
  severity: LolaAuditSeverity;
  capability?: LolaGraphCapabilityId;
  message: string;
  action?: string;
};

export type LolaCapabilityAudit = {
  capability: LolaGraphCapabilityId;
  delegated: { satisfied: boolean; missing: string[] };
  application: { satisfied: boolean; missing: string[] };
  bot?: { satisfied: boolean; missing: string[] };
  supported: boolean;
  notes?: string;
};

export type LolaMicrosoft365AuditReport = {
  mailboxBound: boolean;
  tenantBound: boolean;
  authModeHints: GraphPermissionMode[];
  findings: LolaAuditFinding[];
  capabilities: LolaCapabilityAudit[];
};

export const LOLA_MICROSOFT_365_CAPABILITY_MATRIX: LolaCapabilityRequirement[] = [
  {
    id: "mail.read",
    surface: "mail",
    description: "Read inbox contents for the bound mailbox.",
    delegated: ["Mail.Read"],
    application: ["Mail.Read"],
  },
  {
    id: "mail.search",
    surface: "mail",
    description: "Search mailbox content via Graph queries.",
    delegated: ["Mail.Read"],
    application: ["Mail.Read"],
    notes:
      "Graph mailbox search is covered by mail read permission, not a separate Mail.Search scope.",
  },
  {
    id: "mail.read.thread",
    surface: "mail",
    description: "Read full thread context, attachments metadata, and conversation state.",
    delegated: ["Mail.Read"],
    application: ["Mail.Read"],
  },
  {
    id: "mail.draft",
    surface: "mail",
    description: "Create drafts in the mailbox.",
    delegated: ["Mail.ReadWrite"],
    application: ["Mail.ReadWrite"],
  },
  {
    id: "mail.send",
    surface: "mail",
    description: "Send outbound messages as the mailbox.",
    delegated: ["Mail.Send"],
    application: ["Mail.Send"],
    notes: "Production send flow usually also needs Mail.ReadWrite if drafts are created or moved.",
  },
  {
    id: "mail.reply",
    surface: "mail",
    description: "Reply or reply-all from existing messages.",
    delegated: ["Mail.ReadWrite", "Mail.Send"],
    application: ["Mail.ReadWrite", "Mail.Send"],
  },
  {
    id: "mail.move",
    surface: "mail",
    description: "Move, archive, or re-file messages between folders.",
    delegated: ["Mail.ReadWrite"],
    application: ["Mail.ReadWrite"],
  },
  {
    id: "mail.categorize",
    surface: "mail",
    description: "Apply categories or update message metadata.",
    delegated: ["Mail.ReadWrite"],
    application: ["Mail.ReadWrite"],
  },
  {
    id: "calendar.read",
    surface: "calendar",
    description: "Read calendar events and meeting context.",
    delegated: ["Calendars.Read"],
    application: ["Calendars.Read"],
  },
  {
    id: "contacts.read",
    surface: "contacts",
    description: "Read contacts if the workflow resolves people from mailbox contacts.",
    delegated: ["Contacts.Read"],
    application: ["Contacts.Read"],
  },
  {
    id: "teams.chat.read",
    surface: "teams",
    description: "Read direct chat messages.",
    delegated: ["Chat.Read"],
    application: ["Chat.Read.All"],
    notes:
      "Application access for chat history is broader than delegated access. Use only if daemon access is required.",
  },
  {
    id: "teams.chat.write",
    surface: "teams",
    description: "Send follow-up messages into chats.",
    delegated: ["Chat.ReadWrite"],
    application: ["Chat.ReadWrite.All"],
    notes: "Chat write via application permission is high impact and should be approval-gated.",
  },
  {
    id: "teams.channel.read",
    surface: "teams",
    description: "Read channel messages and context.",
    delegated: ["ChannelMessage.Read.All"],
    application: ["ChannelMessage.Read.Group"],
    bot: ["ChannelMessage.Read.Group"],
    notes:
      "Teams channel reads often rely on resource-specific consent instead of tenant-wide delegated access.",
  },
  {
    id: "teams.channel.write",
    surface: "teams",
    description: "Send messages into channels when authorized.",
    delegated: ["ChannelMessage.Send"],
    application: ["ChannelMessage.Send"],
    bot: ["ChannelMessage.Send"],
  },
  {
    id: "teams.meeting.read",
    surface: "teams",
    description: "Read meeting details, attendance, and online meeting context.",
    delegated: ["OnlineMeetings.Read", "Calendars.Read"],
    application: ["OnlineMeetings.Read.All", "Calendars.Read"],
  },
  {
    id: "teams.transcript.read",
    surface: "teams",
    description: "Read transcripts or meeting artifacts if tenant policy allows it.",
    delegated: ["OnlineMeetingTranscript.Read.All"],
    application: ["OnlineMeetingTranscript.Read.All"],
    notes: "This is commonly admin-consent gated and often blocked by tenant meeting policies.",
  },
  {
    id: "teams.notifications",
    surface: "teams",
    description: "Receive mentions, notifications, or proactive follow-up triggers.",
    delegated: ["Chat.Read", "ChannelMessage.Read.All"],
    application: ["Chat.Read.All", "ChannelMessage.Read.Group"],
    bot: ["Chat.ReadBasic", "ChannelMessage.Read.Group"],
    notes:
      "Notifications require both data access and an eventing model such as subscriptions or Bot Framework activities.",
  },
];

function splitPermissionList(raw: string | undefined): string[] {
  return (
    raw
      ?.split(/[\s,]+/)
      .map((value) => value.trim())
      .filter(Boolean) ?? []
  );
}

export function decodeJwtClaims(token: string): Record<string, unknown> | undefined {
  const parts = token.split(".");
  if (parts.length < 2) {
    return undefined;
  }
  const payload = parts[1] ?? "";
  const padded = payload.padEnd(payload.length + ((4 - (payload.length % 4)) % 4), "=");
  const normalized = padded.replace(/-/g, "+").replace(/_/g, "/");
  try {
    const body = Buffer.from(normalized, "base64").toString("utf8");
    const parsed = JSON.parse(body) as Record<string, unknown>;
    return parsed && typeof parsed === "object" ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function unique(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

function collectStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return unique(value.map((item) => String(item)));
  }
  if (typeof value === "string") {
    return unique(value.split(/[\s,]+/));
  }
  return [];
}

export function resolveLolaMicrosoft365Env(
  env: NodeJS.ProcessEnv = process.env,
): LolaMicrosoft365Env {
  const token = env.LOLA_M365_GRAPH_ACCESS_TOKEN?.trim();
  const claims = token ? decodeJwtClaims(token) : undefined;
  const delegatedScopes = unique([
    ...splitPermissionList(env.LOLA_M365_DELEGATED_SCOPES),
    ...collectStringArray(claims?.scp),
  ]);
  const applicationRoles = unique([
    ...splitPermissionList(env.LOLA_M365_APPLICATION_ROLES),
    ...collectStringArray(claims?.roles),
  ]);
  const botScopes = unique(splitPermissionList(env.LOLA_M365_TEAMS_BOT_SCOPES));

  const authModeHints: GraphPermissionMode[] = [];
  if (delegatedScopes.length > 0) {
    authModeHints.push("delegated");
  }
  if (applicationRoles.length > 0 || (env.LOLA_M365_CLIENT_ID && env.LOLA_M365_CLIENT_SECRET)) {
    authModeHints.push("application");
  }
  if (botScopes.length > 0 || env.MSTEAMS_APP_ID || env.MSTEAMS_APP_PASSWORD) {
    authModeHints.push("bot");
  }

  return {
    tenantId: env.LOLA_M365_TENANT_ID?.trim() || env.MSTEAMS_TENANT_ID?.trim(),
    clientId: env.LOLA_M365_CLIENT_ID?.trim(),
    clientSecret: env.LOLA_M365_CLIENT_SECRET?.trim(),
    mailboxUpn: env.LOLA_M365_MAILBOX_UPN?.trim(),
    expectedUserPrincipalName:
      env.LOLA_M365_EXPECTED_UPN?.trim() || env.LOLA_M365_MAILBOX_UPN?.trim(),
    expectedTenantId: env.LOLA_M365_EXPECTED_TENANT_ID?.trim() || env.LOLA_M365_TENANT_ID?.trim(),
    delegatedScopes,
    applicationRoles,
    botScopes,
    accessTokenClaims: claims,
    authModeHints,
  };
}

function auditCapability(
  requirement: LolaCapabilityRequirement,
  env: LolaMicrosoft365Env,
): LolaCapabilityAudit {
  const delegatedMissing = requirement.delegated.filter(
    (scope) => !env.delegatedScopes?.includes(scope),
  );
  const applicationMissing = requirement.application.filter(
    (role) => !env.applicationRoles?.includes(role),
  );
  const botMissing = requirement.bot?.filter((scope) => !env.botScopes?.includes(scope));

  return {
    capability: requirement.id,
    delegated: { satisfied: delegatedMissing.length === 0, missing: delegatedMissing },
    application: { satisfied: applicationMissing.length === 0, missing: applicationMissing },
    ...(requirement.bot
      ? { bot: { satisfied: (botMissing?.length ?? 0) === 0, missing: botMissing ?? [] } }
      : {}),
    supported:
      delegatedMissing.length === 0 ||
      applicationMissing.length === 0 ||
      (botMissing?.length ?? 1) === 0,
    notes: requirement.notes,
  };
}

export function auditLolaMicrosoft365Access(
  env: LolaMicrosoft365Env,
  options?: { mailboxUpn?: string; tenantId?: string },
): LolaMicrosoft365AuditReport {
  const findings: LolaAuditFinding[] = [];
  const targetMailbox = options?.mailboxUpn?.trim() || env.expectedUserPrincipalName;
  const targetTenantId = options?.tenantId?.trim() || env.expectedTenantId;
  const tokenTenantId =
    typeof env.accessTokenClaims?.tid === "string" ? env.accessTokenClaims.tid : undefined;
  const tokenUpn =
    typeof env.accessTokenClaims?.preferred_username === "string"
      ? env.accessTokenClaims.preferred_username
      : typeof env.accessTokenClaims?.upn === "string"
        ? env.accessTokenClaims.upn
        : undefined;

  const mailboxBound = Boolean(targetMailbox && env.mailboxUpn && env.mailboxUpn === targetMailbox);
  const tenantBound = Boolean(targetTenantId && env.tenantId && env.tenantId === targetTenantId);

  if (!env.tenantId) {
    findings.push({
      severity: "missing",
      message: "Microsoft 365 tenant binding is absent.",
      action: "Set LOLA_M365_TENANT_ID to the authorized Entra tenant ID.",
    });
  }
  if (!env.mailboxUpn) {
    findings.push({
      severity: "missing",
      message: "Mailbox binding is absent.",
      action:
        "Set LOLA_M365_MAILBOX_UPN to the authorized mailbox, for example tynski@eldonlandsupply.com.",
    });
  } else if (targetMailbox && env.mailboxUpn !== targetMailbox) {
    findings.push({
      severity: "misconfigured",
      message: `Mailbox binding points to ${env.mailboxUpn}, not ${targetMailbox}.`,
      action: "Correct LOLA_M365_MAILBOX_UPN before enabling production access.",
    });
  }

  if (env.clientId && !env.clientSecret) {
    findings.push({
      severity: "misconfigured",
      message: "Client ID is set without client secret.",
      action: "Supply LOLA_M365_CLIENT_SECRET or remove application auth configuration.",
    });
  }

  if (targetTenantId && env.tenantId && env.tenantId !== targetTenantId) {
    findings.push({
      severity: "misconfigured",
      message: `Tenant binding points to ${env.tenantId}, not expected tenant ${targetTenantId}.`,
      action: "Correct LOLA_M365_TENANT_ID before attempting token acquisition.",
    });
  }

  if (tokenTenantId && env.tenantId && tokenTenantId !== env.tenantId) {
    findings.push({
      severity: "misconfigured",
      message: `Provided Graph token is minted for tenant ${tokenTenantId}, but LOLA is configured for ${env.tenantId}.`,
      action: "Acquire a token from the correct tenant or fix LOLA_M365_TENANT_ID.",
    });
  }

  if (tokenUpn && targetMailbox && tokenUpn.toLowerCase() !== targetMailbox.toLowerCase()) {
    findings.push({
      severity: "misconfigured",
      message: `Provided delegated token belongs to ${tokenUpn}, not ${targetMailbox}.`,
      action:
        "Use a delegated token for the authorized mailbox or switch to application access with mailbox binding.",
    });
  }

  if (env.authModeHints.length === 0) {
    findings.push({
      severity: "blocked",
      message: "No provable Microsoft 365 auth path is configured for LOLA.",
      action:
        "Provide delegated scopes, application roles, or Teams bot configuration and re-run validation.",
    });
  }

  const capabilities = LOLA_MICROSOFT_365_CAPABILITY_MATRIX.map((requirement) =>
    auditCapability(requirement, env),
  );

  for (const capability of capabilities) {
    if (!capability.supported) {
      findings.push({
        severity: "unproven",
        capability: capability.capability,
        message: `Capability ${capability.capability} is not backed by any complete permission set.`,
        action:
          "Grant the minimum delegated, application, or bot permissions required by the matrix before relying on this path.",
      });
    }
  }

  if (env.authModeHints.includes("application") && !env.clientId) {
    findings.push({
      severity: "misconfigured",
      message: "Application mode is implied, but LOLA_M365_CLIENT_ID is missing.",
      action: "Set LOLA_M365_CLIENT_ID or remove application-mode expectations.",
    });
  }

  if (env.authModeHints.includes("bot") && !env.tenantId) {
    findings.push({
      severity: "misconfigured",
      message: "Teams bot mode is implied without tenant binding.",
      action: "Set MSTEAMS_TENANT_ID or LOLA_M365_TENANT_ID.",
    });
  }

  return {
    mailboxBound,
    tenantBound,
    authModeHints: env.authModeHints,
    findings,
    capabilities,
  };
}
