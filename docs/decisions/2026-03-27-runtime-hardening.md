---
title: "2026-03-27 runtime hardening baseline"
summary: "Decisions for pipeline approvals, memory caps, writable approvals state, and credential hygiene"
---

# 2026-03-27 runtime hardening baseline

## Status

Accepted.

## Context

Operational incidents showed repeated failure modes:

- shell pipelines in exec paths did not behave deterministically with host approvals
- unbounded `MEMORY.md` growth degraded memory quality and context efficiency
- over-hardened filesystem settings blocked writes to `exec-approvals.json`
- insecure execution defaults increased prompt-injection blast radius
- credential hygiene was inconsistent after debugging activity

## Decisions

1. **Pipelines always require approval in exec allowlist mode.**
   - Implemented in runtime allowlist evaluation (`evaluateShellAllowlist`).
   - Rationale: consistency across hosts and fail-safe behavior.

2. **Memory lifecycle gets hard caps and an automation path.**
   - Added `scripts/memory-lifecycle.ts` with soft trigger, hard cap, archive, and distill flow.
   - Rationale: prevent memory bloat and preserve durable recall quality.

3. **`exec-approvals.json` must stay writable.**
   - Added explicit docs guidance in exec approvals + runtime hardening docs.
   - Rationale: runtime updates `lastUsedAt` and related metadata.

4. **Secure-by-default execution posture remains mandatory.**
   - Documented deny/allowlist defaults and break-glass process for `full` mode.
   - Rationale: reduce prompt-injection-to-command-execution risk.

5. **Credential rotation and post-debug hygiene are part of operations.**
   - Added runbook checklist and rotation triggers.
   - Rationale: long-lived tokens and verbose logs increase compromise window.

## Rejected alternatives

- **Allow pipelines when every segment is allowlisted.**
  - Rejected because host-level approval behavior is not uniform and this can silently bypass intended review.

- **Rely on manual memory cleanup only.**
  - Rejected because it does not produce deterministic quality control.

- **Make approvals state immutable for tamper resistance.**
  - Rejected because it breaks required runtime writes and causes `EPERM` failures.

## Consequences

- Some previously auto-allowed pipeline commands now require approval.
- Operators must run or schedule memory lifecycle maintenance.
- Hardening guides now include a specific writable carve-out for approvals state.
