---
title: "LOLA architecture phase 1"
summary: "Read-only LOLA scaffolding for OpenClaw with no external side effects"
---

# LOLA architecture phase 1

Phase 1 adds read-only LOLA scaffolding inside OpenClaw, with dashboard-visible metadata and no external actions.

## Goals

- Reuse the existing OpenClaw agent framework and dashboards. Do not introduce a parallel framework.
- Keep Phase 1 dry-run only so future write paths stay behind explicit approvals.
- Define stable data contracts for briefs, inbox triage, calendar risks, open loops, follow-up tasks, approvals, memory facts, and audit records.

## Connected identity

Phase 1 examples should use placeholders instead of live operator details.

- Email: `executive@example.com`
- Read adapter: Outlook or IMAP, configurable
- Calendar source: Outlook, read-only
- Write capability: none in Phase 1

## Agent architecture

Phase 1 scopes these read-only or draft-only components:

- `lola-orchestrator`, routes tasks, tracks run state, deduplicates work, and escalates.
- `lola-inbox-agent`, reads and triages inbox items and produces internal drafts only.
- `lola-calendar-agent`, reads calendars and reports scheduling risks.
- `lola-followthrough-agent`, reads and prioritizes open loops.
- `lola-briefing-agent`, produces executive brief drafts.
- `lola-memory-agent`, proposes memory updates without silent writes.
- `lola-audit-agent`, drafts audit findings.
- `lola-send-gate`, blocks external actions in Phase 1.

## Data contracts

Phase 1 scaffolding includes the following contracts:

- `ExecutiveBrief`
- `InboxTriageItem`
- `CalendarRiskItem`
- `MeetingPrepPack`
- `OpenLoop`
- `FollowUpTask`
- `ApprovalQueueItem`
- `MemoryFact`
- `AuditRecord`

## Extension points

The Phase 1 scaffold stays repo-native and aligns with existing OpenClaw systems.

- Agent registration through the orchestrator layer.
- Scheduling through the OpenClaw cron and job system.
- Memory persistence under workspace-scoped `.lola/` data.
- Logging through existing redaction-aware logging.
- Dashboard registration through a read-only LOLA metadata hook.
- Approval routing through existing queues.

## Security and compliance

- Dry-run is enforced for all external effects.
- Logs should use the existing redaction pipeline for PII handling.
- Action history should remain immutable where the backing system supports it.
- Global and per-agent kill switches should stay available.

## Phase 1 deliverables

- This architecture document.
- Repo-native Phase 1 scaffolding.
- Placeholder prompts and schemas.
- A first-boot initializer that returns in-memory defaults.
- Config defaults under `src/agents/lola/config`.
- A read-only dashboard registration descriptor.
- Focused tests for schemas, registry helpers, and dry-run behavior.

## Next steps

1. Confirm the Phase 1 scope.
2. Wire the scaffold into the next approved execution path.
3. Add explicit approval-backed write flows in a later phase.

## Phase 2 runbook scaffold

- Execution path: repo edit. No API, n8n, or MCP task integration is available in this workspace, so the Phase 2 scaffold stays local.
- Browser rejection: browser automation is not needed because the change is fully repo-native and deterministic.
- Approval-backed writes: internal drafts, memory facts, and open loops can be written only through the in-memory approval scaffold added in Phase 2.
- Dashboard wiring: the LOLA registration now advertises approval-required write surfaces for internal operators.
- Remaining blocker: persistence is still in-memory only. A later phase should bind these flows to the existing durable store.
