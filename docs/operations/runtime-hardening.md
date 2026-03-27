---
title: "Runtime hardening"
summary: "Operational guardrails for exec approvals, memory lifecycle, and credential hygiene"
read_when:
  - Hardening a new OpenClaw deployment
  - Auditing execution safety defaults
  - Running post-incident cleanup
---

# Runtime hardening

This runbook codifies runtime safety defaults that must remain true in production.

## 1) Pipelines in approval-sensitive paths

Shell pipelines (`cmd1 | cmd2`) are treated as approval-required in exec allowlist mode.
Even fully allowlisted segments still require approval.

Why:

- Some host approval layers treat pipelines as a separate risk class.
- Silent auto-allow can become non-deterministic across hosts.
- Prompt-injection payloads often rely on chaining and pipes.

Enforcement:

- Critical operational scripts avoid pipe operators.
- `scripts/ops-hardening-check.ts` fails if critical scripts reintroduce pipelines.

Run:

```bash
node --import tsx scripts/ops-hardening-check.ts
```

## 2) Keep exec approvals writable

`~/.openclaw/exec-approvals.json` is runtime-mutated. OpenClaw updates allowlist metadata like `lastUsedAt` and command provenance.

Requirements:

- Keep file writable by the OpenClaw runtime user.
- Do not set immutable flags (`chattr +i`, filesystem immutable bits).
- Do not lock it read-only via ACLs.

Failure mode:

- Approval metadata writes fail with `EPERM`.
- Execution flow can fail after otherwise valid approvals.

## 3) Secure execution defaults

Required baseline:

- `tools.exec.host: "sandbox"`
- `tools.exec.security: "deny"` for sandbox
- `tools.exec.security: "allowlist"` for gateway or node hosts
- Avoid `tools.exec.security: "full"` outside short-lived break-glass sessions

Break-glass guidance:

- Use `full` only with an explicit end time.
- Log owner, reason, and rollback plan.
- Revert to `allowlist` immediately after the task.

## 4) Memory lifecycle and anti-bloat policy

`MEMORY.md` must stay compact and high-signal.

Caps:

- soft trigger: 180 lines or 10 KB
- hard cap: 220 lines or 12 KB

Behavior:

- check mode fails if hard cap is exceeded
- apply mode archives current memory to `memory/archive/` and writes a distilled snapshot

Commands:

```bash
node --import tsx scripts/memory-lifecycle.ts --check --workspace ~/.openclaw/workspace
node --import tsx scripts/memory-lifecycle.ts --apply --workspace ~/.openclaw/workspace
```

## 5) Credential rotation and secret hygiene

Minimum operational policy:

1. Rotate model API keys on a fixed cadence (recommended every 30 days).
2. Rotate immediately after debugging sessions that print verbose auth or transport data.
3. Review logs before sharing artifacts externally.
4. Prefer short-lived tokens over long-lived static keys.
5. Store secrets in OpenClaw config/env stores, not in scripts or markdown notes.

Post-debug checklist:

- Revoke and replace keys used during debugging.
- Remove sensitive logs from shared channels and tickets.
- Confirm `openclaw status --all` no longer shows stale tokens or unsafe overrides.

## Browser rejection

No browser automation was used. Repo-native code and docs changes were sufficient.
