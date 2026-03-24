import type { IncomingMessage, ServerResponse } from "node:http";
import { createHmac, timingSafeEqual } from "node:crypto";
import { emitDiagnosticEvent } from "../infra/diagnostic-events.js";

export type WebhookRequestHandler = (req: IncomingMessage, res: ServerResponse) => Promise<boolean>;

export type WhatsAppNormalizedEvent = {
  object?: string;
  entryCount: number;
  messageCount: number;
  statusCount: number;
};

export type GraphNormalizedNotification = {
  subscriptionId?: string;
  tenantId?: string;
  resource?: string;
  changeType?: string;
};

export type WebhookEventDispatcher = {
  dispatchWhatsApp: (event: WhatsAppNormalizedEvent) => Promise<void>;
  dispatchGraph: (notification: GraphNormalizedNotification) => Promise<void>;
};

export type InboundWebhookConfig = {
  baseUrl?: string;
  trustProxy: boolean;
  logPayloads: boolean;
  maxBodyBytes: number;
  rateLimitWindowMs: number;
  rateLimitMax: number;
  whatsappVerifyToken?: string;
  whatsappAppSecret?: string;
  graphClientState?: string;
  graphAllowedTenants?: Set<string>;
};

type RateBucket = { count: number; windowStartMs: number };

export function resolveInboundWebhookConfig(env: NodeJS.ProcessEnv): InboundWebhookConfig {
  const graphAllowedTenants = trimOrUndefined(env.GRAPH_ALLOWED_TENANTS)
    ?.split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
  return {
    baseUrl: trimOrUndefined(env.WEBHOOK_BASE_URL),
    trustProxy: parseBoolean(env.TRUST_PROXY),
    logPayloads: parseBoolean(env.LOG_WEBHOOK_PAYLOADS),
    maxBodyBytes: parsePositiveInt(env.WEBHOOK_MAX_BODY_BYTES, 256 * 1024),
    rateLimitWindowMs: parsePositiveInt(env.RATE_LIMIT_WEBHOOK_WINDOW_MS, 60_000),
    rateLimitMax: parsePositiveInt(env.RATE_LIMIT_WEBHOOK_MAX, 120),
    whatsappVerifyToken: trimOrUndefined(env.WHATSAPP_VERIFY_TOKEN),
    whatsappAppSecret: trimOrUndefined(env.WHATSAPP_APP_SECRET),
    graphClientState: trimOrUndefined(env.GRAPH_WEBHOOK_CLIENT_STATE),
    graphAllowedTenants:
      graphAllowedTenants && graphAllowedTenants.length > 0
        ? new Set(graphAllowedTenants)
        : undefined,
  };
}

function trimOrUndefined(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function parseBoolean(value: string | undefined): boolean {
  const normalized = value?.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}

function parsePositiveInt(raw: string | undefined, fallback: number): number {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(body));
}

function sendPlain(res: ServerResponse, status: number, body: string): void {
  res.statusCode = status;
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.end(body);
}

async function readRawBody(req: IncomingMessage, maxBytes: number): Promise<string> {
  return await new Promise((resolve, reject) => {
    let total = 0;
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => {
      total += chunk.length;
      if (total > maxBytes) {
        reject(new Error("payload too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      resolve(Buffer.concat(chunks).toString("utf-8"));
    });
    req.on("error", (err) => {
      reject(err);
    });
  });
}

function validateWhatsAppSignature(params: {
  signatureHeader: string | undefined;
  rawBody: string;
  appSecret: string;
}): boolean {
  const { signatureHeader, rawBody, appSecret } = params;
  const candidate = (signatureHeader ?? "").trim();
  if (!candidate.startsWith("sha256=")) {
    return false;
  }
  const expected = createHmac("sha256", appSecret).update(rawBody, "utf-8").digest("hex");
  const provided = candidate.slice("sha256=".length);
  const expectedBuf = Buffer.from(expected, "hex");
  const providedBuf = Buffer.from(provided, "hex");
  if (
    expectedBuf.length === 0 ||
    providedBuf.length === 0 ||
    expectedBuf.length !== providedBuf.length
  ) {
    return false;
  }
  return timingSafeEqual(expectedBuf, providedBuf);
}

function maskValue(value: string | undefined): string {
  if (!value) {
    return "unset";
  }
  if (value.length <= 8) {
    return "***";
  }
  return `${value.slice(0, 4)}***${value.slice(-4)}`;
}

export function normalizeWhatsAppEvent(payload: unknown): WhatsAppNormalizedEvent {
  const record = typeof payload === "object" && payload ? (payload as Record<string, unknown>) : {};
  const entries = Array.isArray(record.entry) ? record.entry : [];
  let messageCount = 0;
  let statusCount = 0;

  for (const entry of entries) {
    if (!entry || typeof entry !== "object") {
      continue;
    }
    const changes = Array.isArray((entry as Record<string, unknown>).changes)
      ? ((entry as Record<string, unknown>).changes as unknown[])
      : [];
    for (const change of changes) {
      if (!change || typeof change !== "object") {
        continue;
      }
      const value = (change as Record<string, unknown>).value;
      if (!value || typeof value !== "object") {
        continue;
      }
      const v = value as Record<string, unknown>;
      if (Array.isArray(v.messages)) {
        messageCount += v.messages.length;
      }
      if (Array.isArray(v.statuses)) {
        statusCount += v.statuses.length;
      }
    }
  }

  return {
    object: typeof record.object === "string" ? record.object : undefined,
    entryCount: entries.length,
    messageCount,
    statusCount,
  };
}

export function normalizeGraphNotifications(payload: unknown): GraphNormalizedNotification[] {
  const body = typeof payload === "object" && payload ? (payload as Record<string, unknown>) : {};
  const value = Array.isArray(body.value) ? body.value : [];
  return value
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const entry = item as Record<string, unknown>;
      return {
        subscriptionId: typeof entry.subscriptionId === "string" ? entry.subscriptionId : undefined,
        tenantId: typeof entry.tenantId === "string" ? entry.tenantId : undefined,
        resource: typeof entry.resource === "string" ? entry.resource : undefined,
        changeType: typeof entry.changeType === "string" ? entry.changeType : undefined,
      } satisfies GraphNormalizedNotification;
    })
    .filter((item): item is GraphNormalizedNotification => item !== null);
}

function createDefaultDispatcher(): WebhookEventDispatcher {
  return {
    dispatchWhatsApp: async (event) => {
      emitDiagnosticEvent({
        type: "webhook.processed",
        channel: "whatsapp",
        updateType: event.object,
      });
    },
    dispatchGraph: async () => {
      emitDiagnosticEvent({
        type: "webhook.processed",
        channel: "microsoft-graph",
      });
    },
  };
}

export function createInboundWebhookRequestHandler(params: {
  config: InboundWebhookConfig;
  log: {
    info: (msg: string) => void;
    warn: (msg: string) => void;
    error: (msg: string) => void;
  };
  dispatcher?: WebhookEventDispatcher;
}): WebhookRequestHandler {
  const { config, log } = params;
  const dispatcher = params.dispatcher ?? createDefaultDispatcher();
  const rateBuckets = new Map<string, RateBucket>();

  const pruneRateBuckets = (now: number) => {
    if (rateBuckets.size < 4096) {
      return;
    }
    for (const [key, value] of rateBuckets.entries()) {
      if (now - value.windowStartMs > config.rateLimitWindowMs) {
        rateBuckets.delete(key);
      }
    }
  };

  const getClientIp = (req: IncomingMessage): string => {
    const remoteIp = req.socket?.remoteAddress ?? "unknown";
    if (!config.trustProxy) {
      return remoteIp;
    }
    const forwarded = req.headers["x-forwarded-for"];
    if (typeof forwarded === "string") {
      return forwarded.split(",")[0]?.trim() || remoteIp;
    }
    return remoteIp;
  };

  const applyRateLimit = (req: IncomingMessage, pathname: string): boolean => {
    const now = Date.now();
    pruneRateBuckets(now);
    const key = `${getClientIp(req)}:${pathname}`;
    const bucket = rateBuckets.get(key);
    if (!bucket || now - bucket.windowStartMs >= config.rateLimitWindowMs) {
      rateBuckets.set(key, { count: 1, windowStartMs: now });
      return true;
    }
    bucket.count += 1;
    if (bucket.count > config.rateLimitMax) {
      return false;
    }
    return true;
  };

  log.info(
    `webhooks: inbound routes active (/webhooks/whatsapp, /webhooks/microsoft-graph), trustProxy=${config.trustProxy ? "on" : "off"}, rateLimit=${config.rateLimitMax}/${config.rateLimitWindowMs}ms`,
  );
  if (config.baseUrl) {
    log.info(`webhooks: configured base URL ${config.baseUrl}`);
  }

  return async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    const pathname = url.pathname;
    if (pathname !== "/webhooks/whatsapp" && pathname !== "/webhooks/microsoft-graph") {
      return false;
    }

    if (!applyRateLimit(req, pathname)) {
      sendJson(res, 429, { error: "Rate limit exceeded" });
      return true;
    }

    if (pathname === "/webhooks/whatsapp") {
      if (req.method === "GET") {
        const mode = url.searchParams.get("hub.mode") ?? "";
        const verifyToken = url.searchParams.get("hub.verify_token") ?? "";
        const challenge = url.searchParams.get("hub.challenge") ?? "";

        if (!config.whatsappVerifyToken) {
          log.error("webhooks: WHATSAPP_VERIFY_TOKEN is required for GET /webhooks/whatsapp");
          sendJson(res, 500, { error: "Webhook misconfigured" });
          return true;
        }

        if (mode === "subscribe" && verifyToken === config.whatsappVerifyToken) {
          sendPlain(res, 200, challenge);
          return true;
        }
        log.warn("webhooks: whatsapp verification rejected");
        sendJson(res, 403, { error: "Forbidden" });
        return true;
      }

      if (req.method !== "POST") {
        res.statusCode = 405;
        res.setHeader("Allow", "GET, POST");
        sendJson(res, 405, { error: "Method Not Allowed" });
        return true;
      }

      if (!config.whatsappAppSecret) {
        log.error("webhooks: WHATSAPP_APP_SECRET is required for POST /webhooks/whatsapp");
        sendJson(res, 500, { error: "Webhook misconfigured" });
        return true;
      }

      try {
        const rawBody = await readRawBody(req, config.maxBodyBytes);
        const signature =
          typeof req.headers["x-hub-signature-256"] === "string"
            ? req.headers["x-hub-signature-256"]
            : undefined;

        if (
          !validateWhatsAppSignature({
            signatureHeader: signature,
            rawBody,
            appSecret: config.whatsappAppSecret,
          })
        ) {
          log.warn(`webhooks: whatsapp signature rejected from ${getClientIp(req)}`);
          sendJson(res, 401, { error: "Invalid signature" });
          return true;
        }

        const payload = JSON.parse(rawBody) as unknown;
        const normalized = normalizeWhatsAppEvent(payload);
        emitDiagnosticEvent({
          type: "webhook.received",
          channel: "whatsapp",
          updateType: normalized.object,
        });
        await dispatcher.dispatchWhatsApp(normalized);

        if (config.logPayloads) {
          log.info(
            `webhooks: whatsapp event entries=${normalized.entryCount} messages=${normalized.messageCount} statuses=${normalized.statusCount} secret=${maskValue(config.whatsappAppSecret)}`,
          );
        } else {
          log.info(
            `webhooks: whatsapp event entries=${normalized.entryCount} messages=${normalized.messageCount} statuses=${normalized.statusCount}`,
          );
        }
        sendJson(res, 200, { ok: true });
        return true;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        const status = message.includes("payload too large") ? 413 : 400;
        emitDiagnosticEvent({
          type: "webhook.error",
          channel: "whatsapp",
          error: message,
        });
        sendJson(res, status, {
          error: status === 413 ? "Payload too large" : "Invalid payload",
        });
        return true;
      }
    }

    if (req.method !== "POST") {
      res.statusCode = 405;
      res.setHeader("Allow", "POST");
      sendJson(res, 405, { error: "Method Not Allowed" });
      return true;
    }

    const validationToken = url.searchParams.get("validationToken");
    if (validationToken) {
      sendPlain(res, 200, validationToken);
      return true;
    }

    try {
      const rawBody = await readRawBody(req, config.maxBodyBytes);
      const parsed = JSON.parse(rawBody) as unknown;
      const notifications = normalizeGraphNotifications(parsed);

      if (config.graphClientState) {
        const notificationEntries =
          typeof parsed === "object" &&
          parsed &&
          Array.isArray((parsed as { value?: unknown[] }).value)
            ? ((parsed as { value: unknown[] }).value as Array<Record<string, unknown>>)
            : [];
        const invalid = notificationEntries.find(
          (entry) => entry.clientState !== config.graphClientState,
        );
        if (invalid) {
          log.warn("webhooks: microsoft graph clientState rejected");
          sendJson(res, 403, { error: "Invalid clientState" });
          return true;
        }
      }
      if (config.graphAllowedTenants && config.graphAllowedTenants.size > 0) {
        const invalidTenant = notifications.find(
          (entry) => entry.tenantId && !config.graphAllowedTenants?.has(entry.tenantId),
        );
        if (invalidTenant) {
          log.warn(`webhooks: microsoft graph tenant rejected (${invalidTenant.tenantId})`);
          sendJson(res, 403, { error: "Tenant not allowed" });
          return true;
        }
      }

      emitDiagnosticEvent({
        type: "webhook.received",
        channel: "microsoft-graph",
        updateType: "notification",
      });

      for (const notification of notifications) {
        await dispatcher.dispatchGraph(notification);
      }
      log.info(`webhooks: microsoft graph notifications=${notifications.length}`);
      sendJson(res, 202, { ok: true, received: notifications.length });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const status = message.includes("payload too large") ? 413 : 400;
      emitDiagnosticEvent({
        type: "webhook.error",
        channel: "microsoft-graph",
        error: message,
      });
      sendJson(res, status, {
        error: status === 413 ? "Payload too large" : "Invalid payload",
      });
      return true;
    }
  };
}
