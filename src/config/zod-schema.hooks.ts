import { z } from "zod";

export const HookMappingSchema = z
  .object({
    id: z.string().optional(),
    match: z
      .object({
        path: z.string().optional(),
        source: z.string().optional(),
      })
      .optional(),
    action: z.union([z.literal("wake"), z.literal("agent")]).optional(),
    wakeMode: z.union([z.literal("now"), z.literal("next-heartbeat")]).optional(),
    name: z.string().optional(),
    agentId: z.string().optional(),
    sessionKey: z.string().optional(),
    messageTemplate: z.string().optional(),
    textTemplate: z.string().optional(),
    deliver: z.boolean().optional(),
    allowUnsafeExternalContent: z.boolean().optional(),
    channel: z
      .union([
        z.literal("last"),
        z.literal("whatsapp"),
        z.literal("telegram"),
        z.literal("discord"),
        z.literal("irc"),
        z.literal("slack"),
        z.literal("signal"),
        z.literal("imessage"),
        z.literal("msteams"),
      ])
      .optional(),
    to: z.string().optional(),
    model: z.string().optional(),
    thinking: z.string().optional(),
    timeoutSeconds: z.number().int().positive().optional(),
    transform: z
      .object({
        module: z.string(),
        export: z.string().optional(),
      })
      .strict()
      .optional(),
  })
  .strict()
  .optional();

export const InternalHookHandlerSchema = z
  .object({
    event: z.string(),
    module: z.string(),
    export: z.string().optional(),
  })
  .strict();

const HookConfigSchema = z
  .object({
    enabled: z.boolean().optional(),
    env: z.record(z.string(), z.string()).optional(),
  })
  // Hook configs are intentionally open-ended (handlers can define their own keys).
  // Keep enabled/env typed, but allow additional per-hook keys without marking the
  // whole config invalid (which triggers doctor/best-effort loads).
  .passthrough();

const HookInstallRecordSchema = z
  .object({
    source: z.union([z.literal("npm"), z.literal("archive"), z.literal("path")]),
    spec: z.string().optional(),
    sourcePath: z.string().optional(),
    installPath: z.string().optional(),
    version: z.string().optional(),
    installedAt: z.string().optional(),
    hooks: z.array(z.string()).optional(),
  })
  .strict();

export const InternalHooksSchema = z
  .object({
    enabled: z.boolean().optional(),
    handlers: z.array(InternalHookHandlerSchema).optional(),
    entries: z.record(z.string(), HookConfigSchema).optional(),
    load: z
      .object({
        extraDirs: z.array(z.string()).optional(),
      })
      .strict()
      .optional(),
    installs: z.record(z.string(), HookInstallRecordSchema).optional(),
  })
  .strict()
  .optional();

const HooksLolaTeamSchema = z
  .object({
    id: z.string().optional(),
    name: z.string().optional(),
    channel: z.string().optional(),
    to: z.string().optional(),
  })
  .strict();

const HooksLolaAttioSchema = z
  .object({
    workspaceId: z.string().optional(),
    listId: z.string().optional(),
    apiBaseUrl: z.string().optional(),
  })
  .strict();

const HooksLolaOneDriveSchema = z
  .object({
    driveId: z.string().optional(),
    rootPath: z.string().optional(),
  })
  .strict();

export const HooksLolaSchema = z
  .object({
    enabled: z.boolean().optional(),
    workspace: z.string().optional(),
    bridgeBaseUrl: z.string().optional(),
    followThrough: z
      .object({
        enabled: z.boolean().optional(),
        defaultMessage: z.string().optional(),
        schedule: z.string().optional(),
        model: z.string().optional(),
        thinking: z
          .union([
            z.literal("off"),
            z.literal("minimal"),
            z.literal("low"),
            z.literal("medium"),
            z.literal("high"),
          ])
          .optional(),
        timeoutSeconds: z.number().int().positive().optional(),
        lightContext: z.boolean().optional(),
      })
      .strict()
      .optional(),
    auditSchedule: z
      .object({
        enabled: z.boolean().optional(),
        schedule: z.string().optional(),
        timezone: z.string().optional(),
      })
      .strict()
      .optional(),
    teams: z.array(HooksLolaTeamSchema).optional(),
    attio: HooksLolaAttioSchema.optional(),
    onedrive: HooksLolaOneDriveSchema.optional(),
  })
  .strict()
  .optional();

export const HooksGmailSchema = z
  .object({
    account: z.string().optional(),
    label: z.string().optional(),
    topic: z.string().optional(),
    subscription: z.string().optional(),
    pushToken: z.string().optional(),
    hookUrl: z.string().optional(),
    includeBody: z.boolean().optional(),
    maxBytes: z.number().int().positive().optional(),
    renewEveryMinutes: z.number().int().positive().optional(),
    allowUnsafeExternalContent: z.boolean().optional(),
    serve: z
      .object({
        bind: z.string().optional(),
        port: z.number().int().positive().optional(),
        path: z.string().optional(),
      })
      .strict()
      .optional(),
    tailscale: z
      .object({
        mode: z.union([z.literal("off"), z.literal("serve"), z.literal("funnel")]).optional(),
        path: z.string().optional(),
        target: z.string().optional(),
      })
      .strict()
      .optional(),
    model: z.string().optional(),
    thinking: z
      .union([
        z.literal("off"),
        z.literal("minimal"),
        z.literal("low"),
        z.literal("medium"),
        z.literal("high"),
      ])
      .optional(),
  })
  .strict()
  .optional();
