---
title: "LOLA architecture phase 2"
description: "Approved internal LOLA write paths, approval queue behavior, and dashboard surfaces."
---

# LOLA architecture phase 2

Phase 2 keeps external actions blocked by default and adds approval-backed internal writes for drafts, memory facts, open loops, and audit records.

## What changes from phase 1

- `LOLA_WRITE_ENABLED` controls whether any LOLA internal write path can be queued.
- Per-subagent toggles let you enable writes narrowly for `inbox`, `memory`, `calendar`, `briefing`, `followthrough`, and `audit`.
- All internal writes are queued for approval before they are materialized in `.lola/phase2-store.json`.
- External sends still stay behind `SendGate` and are blocked unless an explicit external send policy is enabled.
- Approval intents, decisions, and outcomes are written to the LOLA audit log with sensitive fields redacted.

## Approval lifecycle

1. Agent proposes an internal write.
2. `ApprovalEngine` creates an `ApprovalQueueItem` with `pending` status.
3. Operator approves or rejects the queue item.
4. Only approved items are materialized into durable LOLA storage.
5. The audit log records the request, decision, and write outcome.

## Dashboard surfaces

The LOLA dashboard registration now exposes these panels:

- Drafts awaiting approval
- Approval queue
- Memory updates
- Open loops
- Audit log

## Deployment defaults

Use safe defaults for first rollout:

- `LOLA_WRITE_ENABLED=false`
- `LOLA_DRY_RUN=true`
- Enable per-subagent toggles one at a time during validation

## Rollback

- Set `LOLA_WRITE_ENABLED=false`
- Leave `LOLA_DRY_RUN=true`
- Reject any still-pending queue items
- Revert the Phase 2 commit if code rollback is required
