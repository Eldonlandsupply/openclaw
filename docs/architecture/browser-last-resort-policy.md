# Browser last resort policy

## Policy

Browser automation is not a default execution path. Use it only after direct orchestration paths are exhausted.

## Required pre checks

Before browser use, validate and log that these paths are unavailable or blocked:
---
title: "Browser Last Resort Policy"
summary: "Policy for restricting browser automation to fallback-only scenarios"
summary: "Policy guardrails for browser automation in OpenClaw"
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
Browser automation is permitted only as the final execution layer.

## Policy Statement

OpenClaw must prefer non-browser interfaces in this order:

1. API
2. n8n
3. MCP
4. repo edit
5. DB or storage
6. CLI

## Allowed browser fallback cases

- No API or webhook exists for the target action.
- Required system only exposes a browser workflow.
- Temporary outage blocks all direct interfaces and the task is time critical.

## Disallowed browser fallback cases

- A direct endpoint exists but is slower to implement.
- A CLI command exists and is safe to run.
- The task can be completed with repository edits or storage operations.

## Evidence required in task outputs

- execution path used
- explicit reason each direct path was rejected
- browser action trace if browser fallback was used
- final result and follow up recommendation to remove browser dependency
5. DB/storage
6. CLI
7. provider API
8. browser

## Required Browser Rejection Note

Every task must include `Browser Rejection` text, even when browser is used.

Template:

```text
Browser Rejection: <reason higher-priority layers were sufficient or why browser is required as last resort>
```

## Allowed Browser Use Cases

- Web-only workflows with no stable API.
- Human-like verification steps that require rendered UI state.
- Federated auth flows that cannot be completed via provider API.

## Disallowed Browser Use Cases

- Convenience use when API or CLI paths exist.
- Replacing reliable data APIs with scraping.
- Unbounded navigation without stop criteria.

## Safety Controls

When browser is used:

- Set explicit target URLs and timeouts.
- Capture evidence artifacts for each state transition.
- Restrict secrets exposure in page logs and screenshots.
- Raise escalation if anti-bot defenses or CAPTCHA blocks execution.
