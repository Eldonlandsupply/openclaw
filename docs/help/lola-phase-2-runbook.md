---
title: "LOLA Phase 2 deployment runbook"
description: "Deploy, validate, and roll back approval-backed LOLA internal writes."
---

# LOLA Phase 2 deployment runbook

## Preconditions

- You are on the target branch with the Phase 2 changes applied.
- `pnpm install` has completed.
- You have a clean working tree except for the intended LOLA changes.

## Enablement checklist

1. Leave `LOLA_DRY_RUN=true`.
2. Set `LOLA_WRITE_ENABLED=true` only in the target environment.
3. Enable one subagent toggle at a time.
4. Verify the approval queue fills before any durable record is written.
5. Confirm audit log entries redact sensitive fields.

## Validation commands

```bash
pnpm tsgo
pnpm test -- src/agents/lola/phase2.test.ts src/agents/lola/ops-memory.test.ts
```

Success criteria:

- Approval requests are `pending` before operator action.
- Approved writes transition to `applied`.
- Drafts, memory facts, and open loops appear only after approval.
- Audit logs show redaction for sensitive payload fields.

## Rollback steps

1. Set `LOLA_WRITE_ENABLED=false`.
2. Keep `LOLA_DRY_RUN=true`.
3. Reject or expire remaining queue items.
4. Revert the LOLA Phase 2 commit if the code path must be removed.
