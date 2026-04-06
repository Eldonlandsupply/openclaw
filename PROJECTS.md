# OpenClaw Projects

This repository is home to multiple distinct projects that share infrastructure
but operate independently. This file is the human-readable entry point.

> **Machine-readable registry:** [`projects/index.yaml`](projects/index.yaml)

---

## Active Projects

### [Mission Control](projects/mission-control/)

Web-based operational control plane for the OpenClaw agent ecosystem.  
**Source:** `mission-control/`  
**Status:** Active — Production

The canonical operator interface for managing the agent fleet. Connects directly
to the OpenClaw gateway via WebSocket. No build step, no framework, no dependencies.

→ [Operator README](projects/mission-control/README.md)  
→ [Source files](mission-control/)

---

### [Eldon Land Supply Runtime](projects/eldon-runtime/)

Bespoke Python agent runtime deployed 24/7 on a Raspberry Pi.  
**Source:** `eldon/`  
**Status:** Active — Production

Custom orchestration layer for Eldon Land Supply business automation.
Handles Telegram, Gmail, and Outlook. Integrates Attio CRM. Runs the
Top 100 Action Allowlist with risk-gated execution.

→ [Operator README](projects/eldon-runtime/README.md)  
→ [Source files](eldon/)

---

## Adding a New Project

1. Add an entry to [`projects/index.yaml`](projects/index.yaml)
2. Create `projects/<slug>/project.yaml` (see [`projects/_schema.yaml`](projects/_schema.yaml))
3. Create `projects/<slug>/README.md` (operator runbook)
4. Add `projects/<slug>/links/index.md` (issues, docs, external refs)
5. Add `projects/<slug>/context/` and `projects/<slug>/runbooks/` as needed
6. Do **not** duplicate config or code into the project folder — link to source

---

## Project Governance Conventions

- Every project must have a canonical `slug` (lowercase, hyphens only)
- Every project must declare an `owner`
- Every project's source code lives in the repo root directory referenced by `related_source`
- Projects are **not** the source — they are binding and governance metadata
- State, logs, and runtime artifacts are **not** committed (see each project's README)
