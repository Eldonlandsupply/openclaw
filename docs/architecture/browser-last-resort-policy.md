---
title: "Browser Last Resort Policy"
summary: "Policy for restricting browser automation to fallback-only scenarios"
---

# Browser Last Resort Policy

Browser automation is fallback-only in OpenClaw orchestration.

## Policy

- Do not use browser automation when a direct system interface exists.
- Browser usage is allowed only after API, n8n, MCP, repo edit, DB/storage, and CLI routes are evaluated and rejected.
- Browser actions must include a recorded justification and rejection reasons for each direct route.

## Acceptable browser fallback scenarios

- A target system has no API, webhook, MCP, CLI, or repo-access path.
- Required operation is only available via interactive web UI.
- Temporary outage or permission boundary blocks direct interfaces, and browser route is explicitly approved by policy.

## Prohibited scenarios

- Convenience-only browser usage when direct APIs or tools are available.
- Browser usage that bypasses policy controls, audit requirements, or approval gates.

## Audit requirements

Any task that uses browser automation must record:

- browser fallback trigger
- direct routes attempted and rejection reasons
- exact browser actions taken
- resulting outputs and follow-up actions
