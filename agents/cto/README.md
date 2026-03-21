# CTO Agent Control Center

## Mission

`agents/cto/` is the operating control center for the OpenClaw CTO
agent. Its job is to keep the repository ecosystem audited,
actionable, and traceable. The standard is operational reality,
known health status, documented risk, explicit next actions, and
evidence-backed remediation plans.

## Scope

This module currently bootstraps governance for repositories that are
directly accessible from the current workspace. In this workspace,
only `openclaw/openclaw` is directly accessible, so the registry and
tracker set are initialized for that repository and mark unavailable
upstream metadata as `UNKNOWN` until a direct integration is added.

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
Each file records the latest scan timestamp, health summary,
unresolved failures, security concerns, stale PR count, and the
single next action that should move the repo toward green status.

### PR completion workflow

PR tracking lives in `agents/cto/repos/pr_tracking/*.json`.
The workflow is:

1. discover open PRs through direct integration
2. classify each PR as merge-ready, blocked, stale, or failing
3. capture exact blocker and next action
4. update after every material state change

If the integration is missing, the tracker must say
`MISSING INTEGRATION` instead of pretending status is known.

### CI remediation workflow

CI tracking lives in `agents/cto/repos/ci_tracking/*.json`.
The workflow is:

1. inventory workflows
2. record recent failures and recurring patterns
3. reproduce locally when possible
4. patch with the smallest safe diff
5. rerun local validation
6. push, observe remote checks, and update remediation notes

### Reporting structure

Reports live in `agents/cto/reports/`.
The baseline cadence is:

- `daily-YYYY-MM-DD.md`
- `weekly-YYYY-MM-DD.md`

Reports must use the mandated CTO status format and be blunt about
risk.

## Execution defaults

- Execution path priority: API, n8n, MCP, repo edit, DB/storage, CLI,
  provider API, browser.
- Browser automation is last resort only.
- Every non-trivial task must record why browser automation was
  rejected.
- Fixes should use minimal safe diffs and explicit validation.
- Never claim completion without known validation status.

## Operational entrypoints

### Manual refresh

Run the full refresh and structural validation locally:

```bash
pnpm cto:run
```

This executes:

1. `pnpm cto:refresh`, which refreshes registry-derived state,
   tracker JSON, and markdown reports.
2. `pnpm cto:validate`, which fails if the control center structure or
   required registry fields are broken.

### Direct script entrypoint

If package scripts are unavailable, run the Python entrypoint directly:

```bash
python3 agents/cto/scripts/refresh_cto_status.py
python3 agents/cto/scripts/refresh_cto_status.py --check
```

### Repeated execution

A scheduled GitHub Actions workflow lives at
`.github/workflows/cto-control-center.yml`. It runs on
`workflow_dispatch`, on pushes that touch `agents/cto/**`, and on a
daily cron to validate the control center and upload the refreshed
state as an artifact.

## State, reports, and configuration

- Config standard: `agents/cto/config/standards.yaml`
- Repo registry: `agents/cto/repos/registry.yaml`
- Health tracking: `agents/cto/repos/health/*.json`
- PR tracking: `agents/cto/repos/pr_tracking/*.json`
- CI tracking: `agents/cto/repos/ci_tracking/*.json`
- Bootstrap state: `agents/cto/state/bootstrap_state.json`
- Last execution log: `agents/cto/state/last_run.json`
- Reports: `agents/cto/reports/*.md`

## Current blockers

- MCP-backed task tracking is `MISSING INTEGRATION` in this workspace.
- No direct GitHub remote or authenticated PR/CI integration is
  available in this checkout, so upstream repo health remains unknown.
- Cross-repository coverage is limited to repositories physically
  accessible from this workspace.

## Operator expectations

- Unknown upstream data must stay `UNKNOWN` or
  `MISSING INTEGRATION` until a direct integration exists.
- Browser automation is rejected unless every higher-priority
  execution path is unavailable.
- Local validation is necessary but not sufficient. Upstream CI, PR,
  and dependency health still need direct provider telemetry before
  the ecosystem can be called fully green.
