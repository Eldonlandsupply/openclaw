# Eldon Land Supply — OpenClaw Runtime

This directory contains the **Eldon Land Supply custom OpenClaw runtime** — a production Python agent
system built on top of, and deployed alongside, the upstream [openclaw/openclaw](https://github.com/openclaw/openclaw) platform.

## History

This code was originally maintained in the standalone repository `Eldonlandsupply/EldonOpenClaw`.
It was consolidated into this repository on **2026-03-15** to create a single canonical source of truth
for all Eldon Land Supply AI infrastructure.

**Source repo retired:** `Eldonlandsupply/EldonOpenClaw` (archived, see deprecation notice there)  
**Consolidation date:** 2026-03-15  
**Performed by:** Automated consolidation via Claude

## What this is

A bespoke Python agent runtime that runs 24/7 on a Raspberry Pi at Eldon Land Supply. It is **not**
the same codebase as the upstream TypeScript openclaw — it is a custom Python orchestration layer that:

- Connects via Telegram, Gmail, and Outlook to receive and send messages
- Routes requests through a risk-gated action execution pipeline
- Runs the Top 100 Action Allowlist for business automation
- Integrates with Attio CRM
- Maintains a semantic memory system (ChromaDB/FAISS)

## Directory Structure

```
eldon/
├── src/openclaw/          # Core Python runtime (connectors, chat, actions, integrations)
├── action_allowlist/      # 100 catalogued business automation actions + governance docs
├── gateway/               # Eldon gateway pipeline (auth, risk, pipeline, handlers)
├── memory-system/         # Repo memory daemon + semantic search (ChromaDB/FAISS)
├── docs/                  # Pi setup guide, deployment docs, operations runbook
├── deploy/                # systemd service files
├── scripts/               # Pi bootstrap, install, start/stop scripts + doctor.py
├── tests/                 # Python test suite
├── config/                # config.yaml, requirements.txt, pyproject.toml, .env.example
└── .github/workflows/     # CI workflow (Python 3.11/3.12)
```

## Deployment

Deployed on Raspberry Pi at `/opt/openclaw`. Service managed by systemd as `openclaw.service`.

See `docs/OpenClaw_Pi_FULL_SETUP.md` for the complete setup guide.
For canonical install, drift audit, and reconciliation of the systemd unit, use
`docs/systemd-service-management.md`.

## What was intentionally excluded from consolidation

- `data/openclaw.db` — runtime SQLite database (not committed; runtime artifact)
- `logs/` content — runtime log files (not committed)
- `.env` — secrets file (never committed; see `config/env.example`)
- `action_allowlist/audit_log.jsonl` — preserved as historical record only

## Relationship to upstream openclaw

This Python runtime is **independent** of the upstream TypeScript `openclaw/openclaw` codebase in
this same repo. They share a name and conceptual purpose (personal AI assistant) but are separate
implementations targeting different use cases:

|            | Upstream openclaw (TypeScript)           | Eldon runtime (Python, `eldon/`)          |
| ---------- | ---------------------------------------- | ----------------------------------------- |
| Purpose    | General-purpose personal AI              | Business automation for Eldon Land Supply |
| Platform   | Multi-platform (macOS, Linux, Windows)   | Raspberry Pi only                         |
| Channels   | WhatsApp, Telegram, Slack, Discord, etc. | Telegram, Gmail, Outlook                  |
| Runtime    | Node.js                                  | Python 3.11+                              |
| Deployment | npm install                              | systemd on Pi                             |
