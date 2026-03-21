# CTO Agent Control Center

## Mission

`agents/cto/` is the operating control center for the OpenClaw CTO agent. Its job is to keep the repository ecosystem audited, actionable, and traceable. The standard is operational reality: known health status, documented risk, explicit next actions, and evidence-backed remediation plans.

## Scope

This module currently bootstraps governance for repositories that are directly accessible from the current workspace. On first bootstrap, only the `openclaw/openclaw` repository was directly accessible, so the registry and tracker set are initialized for that repository and mark all unavailable upstream metadata as `UNKNOWN` until a direct integration is added.

## Control Model

### Repository registry model

The canonical registry lives in `agents/cto/repos/registry.yaml`.
Each repository record captures:

- identity, ownership, and purpose
- runtime stack and package tooling
- build, lint, test, and deploy commands
- CI workflow inventory
- secrets and environment dependencies
- critical paths and maintainers
- branch protection expectations
- production impact, last known green signal, and current risk status

### Health monitoring model

Health state is stored per repository in `agents/cto/repos/health/*.json`.
Each file records the latest scan timestamp, health summary, unresolved failures, security concerns, stale PR count, and the single next action that should move the repo toward green status.

### PR completion workflow

PR tracking lives in `agents/cto/repos/pr_tracking/*.json`.
The workflow is:

1. discover open PRs through direct integration
2. classify each PR as merge-ready, blocked, stale, or failing
3. capture exact blocker and next action
4. update after every material state change

If the integration is missing, the tracker must say `MISSING INTEGRATION` instead of pretending status is known.

### CI remediation workflow

CI tracking lives in `agents/cto/repos/ci_tracking/*.json`.
The workflow is:

1. inventory workflows
2. record recent failures and recurring patterns
3. reproduce locally when possible
4. patch with the smallest safe diff
5. rerun local validation
6. push, observe remote checks, and update remediation notes

### Escalation logic

Escalate only for:

- missing credentials
- missing integrations
- policy blocks
- destructive or high-risk changes
- repeated failure without confident root cause

Unknown data is logged as `UNKNOWN` or `MISSING INTEGRATION`, never hidden.

### Reporting structure

Reports live in `agents/cto/reports/`.
The baseline cadence is:

- `daily-YYYY-MM-DD.md`
- `weekly-YYYY-MM-DD.md`

Reports must use the mandated CTO status format and be blunt about risk.

## Execution defaults

- Execution path priority: API, n8n, MCP, repo edit, DB/storage, CLI, provider API, browser.
- Browser automation is last resort only.
- Every non-trivial task must record why browser automation was rejected.
- Fixes should use minimal safe diffs and explicit validation.
- Never claim completion without known validation status.

## Current gaps

- MCP-backed task tracking is `MISSING INTEGRATION` in this workspace.
- No direct GitHub remote or authenticated PR/CI integration was available during bootstrap.
- Cross-repository coverage is limited to repositories physically accessible from this workspace.
