# Security Policy

If you believe you've found a security issue in OpenClaw, please report it privately.

## Reporting

Report vulnerabilities directly to the repository where the issue lives:

- **Core CLI and gateway** — [openclaw/openclaw](https://github.com/openclaw/openclaw)
- **macOS desktop app** — [openclaw/openclaw](https://github.com/openclaw/openclaw) (apps/macos)
- **iOS app** — [openclaw/openclaw](https://github.com/openclaw/openclaw) (apps/ios)
- **Android app** — [openclaw/openclaw](https://github.com/openclaw/openclaw) (apps/android)
- **ClawHub** — [openclaw/clawhub](https://github.com/openclaw/clawhub)
- **Trust and threat model** — [openclaw/trust](https://github.com/openclaw/trust)

For issues that don't fit a specific repo, or if you're unsure, email **security@openclaw.ai** and we'll route it.

For full reporting instructions see our [Trust page](https://trust.openclaw.ai).

### Required in Reports

1. **Title**
2. **Severity Assessment**
3. **Impact**
4. **Affected Component**
5. **Technical Reproduction**
6. **Demonstrated Impact**
7. **Environment**
8. **Remediation Advice**

Reports without reproduction steps, demonstrated impact, and remediation advice will be deprioritized. Given the volume of AI-generated scanner findings, we must ensure we're receiving vetted reports from researchers who understand the issues.

## Security & Trust

**Jamieson O'Reilly** ([@theonejvo](https://twitter.com/theonejvo)) is Security & Trust at OpenClaw. Jamieson is the founder of [Dvuln](https://dvuln.com) and brings extensive experience in offensive security, penetration testing, and security program development.

## Bug Bounties

OpenClaw is a labor of love. There is no bug bounty program and no budget for paid reports. Please still disclose responsibly so we can fix issues quickly.
The best way to help the project right now is by sending PRs.

## Out of Scope

- Public Internet Exposure
- Using OpenClaw in ways that the docs recommend not to
- Prompt injection attacks

## Operational Guidance

For threat model + hardening guidance (including `openclaw security audit --deep` and `--fix`), see:

- `https://docs.openclaw.ai/gateway/security`
- `https://docs.openclaw.ai/operations/runtime-hardening`

### Exec approvals state file

`~/.openclaw/exec-approvals.json` is write-active runtime state. OpenClaw updates
fields like `lastUsedAt` during execution. Do not make this file immutable or
read-only, or host execution can fail with `EPERM`.

### Web Interface Safety

OpenClaw's web interface is intended for local use only. Do **not** bind it to the public internet; it is not hardened for public exposure.

## Runtime Requirements

### Node.js Version

OpenClaw requires **Node.js 22.12.0 or later** (LTS). This version includes important security patches:

- CVE-2025-59466: async_hooks DoS vulnerability
- CVE-2026-21636: Permission model bypass vulnerability

Verify your Node.js version:

```bash
node --version  # Should be v22.12.0 or later
```

### Docker Security

When running OpenClaw in Docker:

1. The official image runs as a non-root user (`node`) for reduced attack surface
2. Use `--read-only` flag when possible for additional filesystem protection
3. Limit container capabilities with `--cap-drop=ALL`

Example secure Docker run:

```bash
docker run --read-only --cap-drop=ALL \
  -v openclaw-data:/app/data \
  openclaw/openclaw:latest
```

## Security Scanning

This project uses `detect-secrets` for automated secret detection in CI/CD.
See `.detect-secrets.cfg` for configuration and `.secrets.baseline` for the baseline.

Run locally:

```bash
pip install detect-secrets==1.5.0
detect-secrets scan --baseline .secrets.baseline
```

## Credential rotation baseline

- Rotate model/API tokens on a fixed cadence, recommended every 30 days.
- Rotate immediately after debugging sessions that may expose auth or transport logs.
- Review logs before sharing support bundles externally.
- Prefer short-lived credentials and avoid storing secrets in markdown/script files.

## LOLA secrets and WhatsApp command authorization

As of March 24, 2026, LOLA production runs enforce strict WhatsApp command sender authorization and Microsoft Graph secret validation at startup.

Required controls:

- `WHATSAPP_CEO_PRIMARY_NUMBER` must be set when `LOLA_ENABLED=true`.
- Optional assistants can be set via `WHATSAPP_AUTHORIZED_ASSISTANTS`.
- Optional additional command-authorized numbers can be set via `WHATSAPP_ALLOWED_NUMBERS`.
- Microsoft Graph-enabled LOLA runs require tenant, client, secret, and mailbox values (`M365_*` or `LOLA_M365_*` aliases).
- Microsoft token cache path must use encrypted cache filename suffix `.enc.json`.

Secrets storage:

- Store `.env` in `~/.openclaw/.env`.
- Repo-local `.env` is rejected by default unless `OPENCLAW_ALLOW_REPO_ENV=1` is set.
- Keep Graph token cache under `~/.openclaw/credentials/m365/` and out of git.
