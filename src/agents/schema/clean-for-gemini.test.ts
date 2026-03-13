import { describe, expect, it } from "vitest";
import { cleanSchemaForGemini } from "./clean-for-gemini.js";

describe("cleanSchemaForGemini", () => {
  it("removes date-time format constraints from nested task schemas", () => {
    const taskItemSchema = {
      type: "object",
      properties: {
        logs: {
          type: "array",
          items: {
            type: "object",
            properties: {
              timestamp: { type: "string", format: "date-time" },
              level: {
                type: "string",
                enum: ["debug", "info", "warn", "error"],
              },
              message: { type: "string" },
            },
            required: ["timestamp", "level", "message"],
          },
        },
        created_at: { type: "string", format: "date-time" },
        updated_at: { type: "string", format: "date-time" },
      },
      required: ["logs", "created_at", "updated_at"],
    };

    const cleaned = cleanSchemaForGemini(taskItemSchema) as {
      properties: {
        logs: { items: { properties: { timestamp: Record<string, unknown> } } };
        created_at: Record<string, unknown>;
        updated_at: Record<string, unknown>;
      };
    };

    expect(cleaned.properties.logs.items.properties.timestamp).toEqual({ type: "string" });
    expect(cleaned.properties.created_at).toEqual({ type: "string" });
    expect(cleaned.properties.updated_at).toEqual({ type: "string" });
  });
});
