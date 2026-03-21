import { describe, expect, it } from "vitest";
import {
  LOLA_MICROSOFT_365_CAPABILITY_MATRIX,
  auditLolaMicrosoft365Access,
  resolveLolaMicrosoft365Env,
} from "./microsoft365-audit.js";

describe("lola microsoft 365 audit", () => {
  it("flags missing mailbox and auth configuration", () => {
    const env = resolveLolaMicrosoft365Env({});
    const report = auditLolaMicrosoft365Access(env, {
      mailboxUpn: "tynski@eldonlandsupply.com",
      tenantId: "tenant-123",
    });

    expect(report.mailboxBound).toBe(false);
    expect(report.tenantBound).toBe(false);
    expect(report.findings.some((finding) => finding.severity === "blocked")).toBe(true);
    expect(
      report.findings.some((finding) => finding.message.includes("Mailbox binding is absent")),
    ).toBe(true);
  });

  it("accepts delegated mail scopes and application chat scopes independently", () => {
    const env = resolveLolaMicrosoft365Env({
      LOLA_M365_TENANT_ID: "tenant-123",
      LOLA_M365_CLIENT_ID: "client-123",
      LOLA_M365_CLIENT_SECRET: "secret-123",
      LOLA_M365_MAILBOX_UPN: "tynski@eldonlandsupply.com",
      LOLA_M365_DELEGATED_SCOPES: [
        "Mail.Read",
        "Mail.ReadWrite",
        "Mail.Send",
        "Calendars.Read",
        "Contacts.Read",
      ].join(" "),
      LOLA_M365_APPLICATION_ROLES: [
        "Chat.Read.All",
        "Chat.ReadWrite.All",
        "ChannelMessage.Read.Group",
        "ChannelMessage.Send",
        "OnlineMeetings.Read.All",
        "OnlineMeetingTranscript.Read.All",
        "Calendars.Read",
      ].join(","),
      LOLA_M365_TEAMS_BOT_SCOPES: "ChannelMessage.Read.Group ChannelMessage.Send Chat.ReadBasic",
    });

    const report = auditLolaMicrosoft365Access(env, {
      mailboxUpn: "tynski@eldonlandsupply.com",
      tenantId: "tenant-123",
    });

    expect(report.mailboxBound).toBe(true);
    expect(report.tenantBound).toBe(true);
    expect(report.capabilities.every((capability) => capability.supported)).toBe(true);
    expect(report.findings.some((finding) => finding.severity === "misconfigured")).toBe(false);
  });

  it("catches delegated token identity mismatch", () => {
    const token = [
      "header",
      Buffer.from(
        JSON.stringify({
          preferred_username: "other@eldonlandsupply.com",
          tid: "tenant-123",
          scp: "Mail.Read",
        }),
      ).toString("base64url"),
      "sig",
    ].join(".");

    const env = resolveLolaMicrosoft365Env({
      LOLA_M365_TENANT_ID: "tenant-123",
      LOLA_M365_MAILBOX_UPN: "tynski@eldonlandsupply.com",
      LOLA_M365_GRAPH_ACCESS_TOKEN: token,
    });

    const report = auditLolaMicrosoft365Access(env, {
      mailboxUpn: "tynski@eldonlandsupply.com",
      tenantId: "tenant-123",
    });

    expect(
      report.findings.some((finding) =>
        finding.message.includes("Provided delegated token belongs to other@eldonlandsupply.com"),
      ),
    ).toBe(true);
  });

  it("keeps permission matrix grounded in exact capability IDs", () => {
    expect(LOLA_MICROSOFT_365_CAPABILITY_MATRIX.map((entry) => entry.id)).toEqual([
      "mail.read",
      "mail.search",
      "mail.read.thread",
      "mail.draft",
      "mail.send",
      "mail.reply",
      "mail.move",
      "mail.categorize",
      "calendar.read",
      "contacts.read",
      "teams.chat.read",
      "teams.chat.write",
      "teams.channel.read",
      "teams.channel.write",
      "teams.meeting.read",
      "teams.transcript.read",
      "teams.notifications",
    ]);
  });
});
