import { describe, expect, it } from "vitest";
import {
  buildGraphSubscriptionRequest,
  nextGraphSubscriptionRenewalDate,
} from "./microsoft-graph-subscriptions.js";

describe("microsoft graph subscriptions", () => {
  it("builds subscription payload with defaults", () => {
    const now = new Date("2026-03-24T00:00:00.000Z");
    const payload = buildGraphSubscriptionRequest(
      {
        resource: "users/123/messages",
        notificationUrl: "https://example.com/webhooks/microsoft-graph",
        clientState: "state-1",
      },
      now,
    );

    expect(payload.changeType).toBe("created,updated");
    expect(payload.expirationDateTime).toBe("2026-03-24T01:00:00.000Z");
    expect(payload.clientState).toBe("state-1");
  });

  it("computes renewal date before expiration", () => {
    const renewal = nextGraphSubscriptionRenewalDate("2026-03-24T01:00:00.000Z", 20);
    expect(renewal.toISOString()).toBe("2026-03-24T00:40:00.000Z");
  });
});
