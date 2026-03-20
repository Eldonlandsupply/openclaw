---
title: LOLA Phase 3
description: "Policy-gated external actions, executor scaffolding, and Outlook provider wiring."
---

Phase 3 extends LOLA with policy-backed external action scaffolding. Internal writes still use the approval queue, and external sends remain deterministic through a dry-run-first executor.

## Scope

- Adds a policy engine that scores external actions before execution.
- Adds an executor that records dry-run or executed Outlook actions in the LOLA store.
- Exposes an `externalActions` dashboard surface.
- Keeps audit logging redacted for sensitive fields.

## Guardrails

- Policy checks run before any provider call.
- External actions are logged to the audit trail and the LOLA store.
- Dry run remains the default operating mode.
