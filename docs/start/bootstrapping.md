---
summary: "How bootstrap files should be split and kept small for reliable agent startup"
read_when:
  - Understanding what happens on the first agent run
  - Explaining where bootstrap and memory files live
  - Debugging onboarding identity setup
  - Tightening workspace bootstrap files for child agents
title: "Agent Bootstrapping"
sidebarTitle: "Bootstrapping"
---

# Agent bootstrapping

Bootstrapping is the first-run ritual that prepares an agent workspace and
collects identity details. It happens after onboarding, when the agent starts
for the first time.

The main failure mode is not missing files. It is bloated, mixed-purpose files
that waste context or get truncated before child agents see the critical rules.
Keep each bootstrap file narrow, obvious, and small.

## What bootstrapping does

On the first agent run, OpenClaw bootstraps the workspace (default
`~/.openclaw/workspace`):

- Seeds `AGENTS.md`, `BOOTSTRAP.md`, `IDENTITY.md`, `USER.md`.
- Runs a short Q&A ritual, one question at a time.
- Writes identity and preferences to `IDENTITY.md`, `USER.md`, `SOUL.md`.
- Removes `BOOTSTRAP.md` when finished so it only runs once.

## Split the bootstrap files cleanly

Use each file for one job:

- `AGENTS.md`
  - Non-negotiable operating rules.
  - Session-start checklist.
  - Router rules, child-agent rules, artifact requirements, safety guardrails.
- `SOUL.md`
  - Tone, persona, boundaries, and relationship style.
- `USER.md`
  - Facts about the human, preferences, timezone, working style.
- `TOOLS.md`
  - Local environment notes such as device names, hosts, or tool caveats.
- `BOOTSTRAP.md`
  - One-time first-run interview only.
  - No durable policy. Delete it after setup.
- `BOOT.md`
  - Tiny startup checklist for recurring boot actions.
- `HEARTBEAT.md`
  - Tiny recurring checklist for periodic checks.
- `memory/YYYY-MM-DD.md`
  - Daily append-only log.
- `MEMORY.md`
  - Distilled durable memory, updated by a periodic review pass.

If a rule must survive child-agent spawning or a fresh session, put it in
`AGENTS.md`, not in `BOOTSTRAP.md`, `HEARTBEAT.md`, or an ephemeral chat.

## Keep files under tight budgets

OpenClaw injects workspace files into model context. Smaller files are more
reliable and easier for child agents to follow.

Recommended budgets:

- `AGENTS.md`: under 8 KB, only durable rules.
- `SOUL.md`: under 4 KB.
- `USER.md`: under 4 KB.
- `TOOLS.md`: under 6 KB.
- `BOOTSTRAP.md`: under 4 KB, then delete it after setup.
- `BOOT.md`: under 1 KB.
- `HEARTBEAT.md`: under 1 KB.
- `MEMORY.md`: keep it curated and compact.
- `memory/YYYY-MM-DD.md`: append-only for the current day, then distill later.

These are working budgets, not hard parser limits. If files grow past them,
move stale detail into dated memory files or a repo doc that is loaded only when
needed.

## Immediate-win defaults to encode in AGENTS.md

Put these rules in `AGENTS.md` so they survive fresh sessions and child-agent
spawns:

1. Start every task by routing it through the highest-priority direct interface
   available.
2. Use browser automation only as a last resort, and record why it was rejected
   or required.
3. Require every child agent to return an artifact or explicit "no artifact"
   result.
4. Set conservative default spawn ceilings.
5. Classify tools by risk tier and put destructive or external actions behind
   approval wrappers.
6. Apply compaction or summary rules once context crosses a threshold.
7. Write durable facts to files, not to "mental notes."

## Where it runs

Bootstrapping always runs on the gateway host. If the macOS app connects to a
remote Gateway, the workspace and bootstrapping files live on that remote
machine.

<Note>
When the Gateway runs on another machine, edit workspace files on the gateway
host, for example `user@gateway-host:~/.openclaw/workspace`.
</Note>

## Related docs

- Memory workflow: [Memory](/concepts/memory)
- Workspace layout: [Agent workspace](/concepts/agent-workspace)
- macOS app onboarding: [Onboarding](/start/onboarding)
