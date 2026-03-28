import { Type } from "@sinclair/typebox";
import type { OpenClawConfig } from "../../config/config.js";
import type { AnyAgentTool } from "./common.js";
import { createSessionMemorySpine } from "../../memory/session-memory-spine.js";
import { resolveSessionAgentId } from "../agent-scope.js";
import { jsonResult, readNumberParam, readStringParam } from "./common.js";

const SessionMemorySpineSchema = Type.Object({
  action: Type.Enum({
    start: "start",
    heartbeat: "heartbeat",
    state: "state",
    record: "record",
    checkpoint: "checkpoint",
    context: "context",
    resolve_flag: "resolve_flag",
    compact: "compact",
  }),
  kind: Type.Optional(Type.Enum({ record: "record", log: "log", flag: "flag", task: "task" })),
  content: Type.Optional(Type.String()),
  confidence: Type.Optional(Type.Number()),
  nextState: Type.Optional(
    Type.Enum({ active: "active", interrupted: "interrupted", completed: "completed" }),
  ),
  taskKey: Type.Optional(Type.String()),
  taskStatus: Type.Optional(
    Type.Enum({ todo: "todo", in_progress: "in_progress", done: "done", blocked: "blocked" }),
  ),
  flagThread: Type.Optional(Type.String()),
  maxChars: Type.Optional(Type.Number()),
  recentEventsLimit: Type.Optional(Type.Number()),
  flagId: Type.Optional(Type.Number()),
});

export function createSessionMemorySpineTool(options: {
  config?: OpenClawConfig;
  agentSessionKey?: string;
}): AnyAgentTool | null {
  if (!options.config || !options.agentSessionKey) {
    return null;
  }
  const agentId = resolveSessionAgentId({
    sessionKey: options.agentSessionKey,
    config: options.config,
  });

  return {
    label: "Session Memory Spine",
    name: "session_memory_spine",
    description:
      "Structured persistent session memory for records/logs/flags/tasks, checkpoints, compaction, and resumable session context assembly.",
    parameters: SessionMemorySpineSchema,
    execute: async (_toolCallId, params) => {
      const action = readStringParam(params, "action", { required: true });
      const spine = createSessionMemorySpine({ agentId });
      try {
        if (action === "start") {
          return jsonResult(spine.startOrResumeSession(options.agentSessionKey ?? ""));
        }
        if (action === "heartbeat") {
          spine.touchHeartbeat(options.agentSessionKey ?? "");
          return jsonResult({ ok: true });
        }
        if (action === "state") {
          const nextState = readStringParam(params, "nextState", { required: true });
          spine.transitionSessionState(options.agentSessionKey ?? "", nextState as never);
          return jsonResult({ ok: true, state: nextState });
        }
        if (action === "record") {
          const kind = readStringParam(params, "kind", { required: true });
          const content = readStringParam(params, "content", { required: true });
          const confidence = readNumberParam(params, "confidence");
          const taskKey = readStringParam(params, "taskKey");
          const taskStatus = readStringParam(params, "taskStatus");
          const flagThread = readStringParam(params, "flagThread");
          return jsonResult(
            spine.appendEvent({
              sessionKey: options.agentSessionKey ?? "",
              kind: kind as never,
              content,
              confidence: confidence ?? undefined,
              taskKey: taskKey ?? undefined,
              taskStatus: taskStatus as never,
              flagThread: flagThread ?? undefined,
            }),
          );
        }
        if (action === "checkpoint") {
          const content = readStringParam(params, "content");
          const checkpoint = spine.createCheckpoint(options.agentSessionKey ?? "", {
            note: content ?? "checkpoint",
            at: new Date().toISOString(),
          });
          return jsonResult(checkpoint);
        }
        if (action === "context") {
          const maxChars = readNumberParam(params, "maxChars", { integer: true });
          const recentEventsLimit = readNumberParam(params, "recentEventsLimit", { integer: true });
          return jsonResult(
            spine.assembleContext({
              sessionKey: options.agentSessionKey ?? "",
              maxChars: maxChars ?? undefined,
              recentEventsLimit: recentEventsLimit ?? undefined,
            }),
          );
        }
        if (action === "resolve_flag") {
          const flagId = readNumberParam(params, "flagId", { required: true, integer: true });
          spine.resolveFlag(flagId);
          return jsonResult({ ok: true, flagId });
        }
        if (action === "compact") {
          return jsonResult(
            spine.compactSession({
              sessionKey: options.agentSessionKey ?? "",
            }),
          );
        }
        return jsonResult({ ok: false, error: `Unknown action: ${action}` });
      } finally {
        spine.close();
      }
    },
  };
}
