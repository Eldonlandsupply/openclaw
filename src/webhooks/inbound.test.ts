import { createHmac } from "node:crypto";
import { PassThrough } from "node:stream";
import { describe, expect, it, vi } from "vitest";
import { createInboundWebhookRequestHandler, type InboundWebhookConfig } from "./inbound.js";

type MockReq = PassThrough & {
  method: string;
  url: string;
  headers: Record<string, string>;
  socket: { remoteAddress: string };
};

type MockRes = {
  statusCode: number;
  headersSent: boolean;
  headers: Record<string, string>;
  body: string;
  setHeader: (name: string, value: string) => void;
  end: (body?: string) => void;
};

function createMockReq(params: {
  method: string;
  url: string;
  headers?: Record<string, string>;
  body?: string;
  remoteAddress?: string;
}): MockReq {
  const stream = new PassThrough() as MockReq;
  stream.method = params.method;
  stream.url = params.url;
  stream.headers = params.headers ?? {};
  stream.socket = { remoteAddress: params.remoteAddress ?? "127.0.0.1" };
  stream.end(params.body ?? "");
  return stream;
}

function createMockRes(): MockRes {
  return {
    statusCode: 200,
    headersSent: false,
    headers: {},
    body: "",
    setHeader(name, value) {
      this.headers[name.toLowerCase()] = String(value);
    },
    end(body) {
      this.headersSent = true;
      this.body = body ?? "";
    },
  };
}

function baseConfig(): InboundWebhookConfig {
  return {
    trustProxy: false,
    logPayloads: false,
    maxBodyBytes: 64 * 1024,
    rateLimitWindowMs: 60_000,
    rateLimitMax: 10,
    whatsappVerifyToken: "verify-token",
    whatsappAppSecret: "app-secret",
    graphClientState: "graph-state",
  };
}

function sign(body: string, secret: string): string {
  const digest = createHmac("sha256", secret).update(body, "utf-8").digest("hex");
  return `sha256=${digest}`;
}

describe("inbound webhook handler", () => {
  it("handles WhatsApp GET verification success", async () => {
    const handler = createInboundWebhookRequestHandler({
      config: baseConfig(),
      log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
    });
    const req = createMockReq({
      method: "GET",
      url: "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=verify-token&hub.challenge=abc123",
    });
    const res = createMockRes();

    const handled = await handler(req, res as never);

    expect(handled).toBe(true);
    expect(res.statusCode).toBe(200);
    expect(res.body).toBe("abc123");
  });

  it("handles WhatsApp GET verification failure", async () => {
    const handler = createInboundWebhookRequestHandler({
      config: baseConfig(),
      log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
    });
    const req = createMockReq({
      method: "GET",
      url: "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=abc123",
    });
    const res = createMockRes();

    await handler(req, res as never);

    expect(res.statusCode).toBe(403);
  });

  it("accepts WhatsApp POST with valid signature", async () => {
    const config = baseConfig();
    const dispatchWhatsApp = vi.fn().mockResolvedValue(undefined);
    const handler = createInboundWebhookRequestHandler({
      config,
      log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
      dispatcher: {
        dispatchWhatsApp,
        dispatchGraph: vi.fn().mockResolvedValue(undefined),
      },
    });
    const payload = JSON.stringify({
      object: "whatsapp_business_account",
      entry: [],
    });
    const req = createMockReq({
      method: "POST",
      url: "/webhooks/whatsapp",
      headers: {
        "x-hub-signature-256": sign(payload, config.whatsappAppSecret!),
      },
      body: payload,
    });
    const res = createMockRes();

    await handler(req, res as never);

    expect(res.statusCode).toBe(200);
    expect(dispatchWhatsApp).toHaveBeenCalledTimes(1);
  });

  it("rejects WhatsApp POST with invalid signature", async () => {
    const config = baseConfig();
    const dispatchWhatsApp = vi.fn().mockResolvedValue(undefined);
    const handler = createInboundWebhookRequestHandler({
      config,
      log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
      dispatcher: {
        dispatchWhatsApp,
        dispatchGraph: vi.fn().mockResolvedValue(undefined),
      },
    });
    const payload = JSON.stringify({
      object: "whatsapp_business_account",
      entry: [],
    });
    const req = createMockReq({
      method: "POST",
      url: "/webhooks/whatsapp",
      headers: { "x-hub-signature-256": "sha256=deadbeef" },
      body: payload,
    });
    const res = createMockRes();

    await handler(req, res as never);

    expect(res.statusCode).toBe(401);
    expect(dispatchWhatsApp).not.toHaveBeenCalled();
  });

  it("handles Microsoft Graph validationToken", async () => {
    const handler = createInboundWebhookRequestHandler({
      config: baseConfig(),
      log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
    });
    const req = createMockReq({
      method: "POST",
      url: "/webhooks/microsoft-graph?validationToken=token-value",
    });
    const res = createMockRes();

    await handler(req, res as never);

    expect(res.statusCode).toBe(200);
    expect(res.body).toBe("token-value");
  });

  it("accepts Graph notifications with valid clientState", async () => {
    const dispatchGraph = vi.fn().mockResolvedValue(undefined);
    const handler = createInboundWebhookRequestHandler({
      config: baseConfig(),
      log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
      dispatcher: {
        dispatchWhatsApp: vi.fn().mockResolvedValue(undefined),
        dispatchGraph,
      },
    });
    const payload = JSON.stringify({
      value: [
        {
          subscriptionId: "sub-1",
          clientState: "graph-state",
          resource: "users/user-id/messages",
          changeType: "created",
        },
      ],
    });
    const req = createMockReq({
      method: "POST",
      url: "/webhooks/microsoft-graph",
      body: payload,
    });
    const res = createMockRes();

    await handler(req, res as never);

    expect(res.statusCode).toBe(202);
    expect(dispatchGraph).toHaveBeenCalledTimes(1);
  });

  it("rejects Graph notifications with invalid clientState", async () => {
    const dispatchGraph = vi.fn().mockResolvedValue(undefined);
    const handler = createInboundWebhookRequestHandler({
      config: baseConfig(),
      log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
      dispatcher: {
        dispatchWhatsApp: vi.fn().mockResolvedValue(undefined),
        dispatchGraph,
      },
    });
    const payload = JSON.stringify({
      value: [
        {
          subscriptionId: "sub-1",
          clientState: "bad-state",
          resource: "users/user-id/messages",
          changeType: "created",
        },
      ],
    });
    const req = createMockReq({
      method: "POST",
      url: "/webhooks/microsoft-graph",
      body: payload,
    });
    const res = createMockRes();

    await handler(req, res as never);

    expect(res.statusCode).toBe(403);
    expect(dispatchGraph).not.toHaveBeenCalled();
  });

  it("enforces webhook rate limits", async () => {
    const config = baseConfig();
    config.rateLimitMax = 1;
    const handler = createInboundWebhookRequestHandler({
      config,
      log: { info: vi.fn(), warn: vi.fn(), error: vi.fn() },
    });

    const first = createMockReq({
      method: "GET",
      url: "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=verify-token&hub.challenge=abc123",
      remoteAddress: "10.0.0.5",
    });
    const second = createMockReq({
      method: "GET",
      url: "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=verify-token&hub.challenge=abc123",
      remoteAddress: "10.0.0.5",
    });
    const firstRes = createMockRes();
    const secondRes = createMockRes();

    await handler(first, firstRes as never);
    await handler(second, secondRes as never);

    expect(firstRes.statusCode).toBe(200);
    expect(secondRes.statusCode).toBe(429);
  });
});
