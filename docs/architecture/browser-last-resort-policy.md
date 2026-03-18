---
title: "Browser Last Resort Policy"
summary: "Policy guardrails for browser automation in OpenClaw"
---

# Browser Last Resort Policy

Browser automation is fallback-only in OpenClaw orchestration.

## Policy

- Do not use browser automation when a direct system interface exists.
- Browser usage is allowed only after API, n8n, MCP, repo edit, DB/storage, CLI, and provider API routes are evaluated and rejected.
- Browser actions must include a recorded justification and rejection reasons for each direct route.

## Required pre-checks

Before browser use, validate and log that higher-priority routes are unavailable, blocked, or insufficient.

## Acceptable browser fallback scenarios

- A target system has no API, webhook, MCP, CLI, or repo-access path.
- The required operation is available only through an interactive web UI.
- A temporary outage or permission boundary blocks direct interfaces, and browser use is still policy-compliant.

## Prohibited scenarios

- Convenience-only browser usage when direct APIs or tools are available.
- Browser usage that bypasses policy controls, audit requirements, or approval gates.
- Unbounded navigation without stop criteria.

## Required Browser Rejection note

Every task must include `Browser Rejection` text, even when browser is used.

Template:

```text
Browser Rejection: <reason higher-priority layers were sufficient or why browser is required as last resort>
```

## Audit requirements

Any task that uses browser automation must record:

- browser fallback trigger
- direct routes attempted and rejection reasons
- exact browser actions taken
- resulting outputs and follow-up actions

## Safety controls

When browser is used:

- Set explicit target URLs and timeouts.
- Capture evidence artifacts for each state transition.
- Restrict secrets exposure in page logs and screenshots.
- Escalate if anti-bot defenses or CAPTCHA block execution.
