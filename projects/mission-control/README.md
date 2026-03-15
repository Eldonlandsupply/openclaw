# OpenClaw Mission Control

**Canonical project home:** `projects/mission-control/`  
**Source files:** `mission-control/` (root of repo)  
**Status:** Active — Production  
**Owner:** Eldonlandsupply  

---

## What This Project Does

Mission Control is the operator-grade web interface for the OpenClaw agent ecosystem.
It is a single-page HTML/CSS/JS application that connects directly to the OpenClaw
gateway via WebSocket, speaks the native gateway protocol, and provides a full
control plane for managing agents, sessions, channels, cron jobs, policies, and
live monitoring.

**This is not a toy admin panel.** It is the canonical control surface from which
an operator governs the entire agent fleet.

---

## Why It Exists

OpenClaw's gateway exposes a rich WebSocket API covering agents, sessions, cron,
hooks, channels, logs, and config. Mission Control makes that API operable by
humans — without requiring CLI commands, raw JSON, or script-writing.

---

## What Systems It Touches

| System | How |
|--------|-----|
| OpenClaw Gateway | WebSocket (ws:// or wss://) — native protocol frames |
| Agent configs | Via `agents.list`, `agents.create`, `agents.update`, `agents.delete` |
| Agent files (prompts, skills) | Via `agents.files.list`, `agents.files.get`, `agents.files.set` |
| Sessions | Via `sessions.list`, `sessions.preview`, `sessions.reset`, `sessions.delete` |
| Channels | Via `channels.status` |
| Cron jobs | Via `cron.list`, `cron.add`, `cron.run`, `cron.remove` |
| Models | Via `models.list` |
| Gateway config | Via `config.get`, `config.set` |
| Logs | Via `logs.tail` |
| Nodes | Via `nodes.list` |
| Exec Approvals | Via `execApprovals.list`, `execApprovals.approve`, `execApprovals.reject` |
| Skills | Via `skills.list`, `skills.update` |
| Devices | Via `devices.list` |
| Usage/cost | Via `usage.sessions` |

---

## How to Run It

### Local (no server required)
```bash
open mission-control/index.html
```
Enter gateway URL (default `ws://127.0.0.1:18789`), token, and password.

### Static server
```bash
cd mission-control
python3 -m http.server 8080
# Open http://localhost:8080
```

### Remote gateway
Use `wss://your-host:18789` for TLS-secured remote gateways.

---

## How Agents Interact With This Project

Mission Control does **not** run as an agent. It is the human control surface
that governs agents. Agents appear as managed entities within Mission Control,
not as operators of it.

Future: a `mission-control-monitor` agent may be added to watch for anomalies,
alert on failures, and surface recommendations — but it would be a separate
agent entity, not this interface itself.

---

## Authoritative Files

| File | Purpose |
|------|---------|
| `mission-control/index.html` | DOM structure and shell layout |
| `mission-control/mc.css` | Design system, component styles |
| `mission-control/mc.js` | Gateway client + all view logic |
| `mission-control/README.md` | User-facing readme |
| `projects/mission-control/project.yaml` | Project identity and metadata |
| `projects/mission-control/README.md` | This operator runbook |
| `projects/mission-control/context/capabilities.md` | Gateway API surface used |
| `projects/mission-control/runbooks/` | Operational runbooks |
| `projects/mission-control/links/index.md` | Issues, PRs, external references |

---

## Common Operations

```bash
# Run locally (macOS)
open mission-control/index.html

# Run with a static server
cd mission-control && python3 -m http.server 8080

# Check gateway is reachable
curl -v ws://127.0.0.1:18789  # Should upgrade to WebSocket

# Check gateway auth
# In Mission Control: enter URL + token in connection panel
```

---

## Risks and Open Questions

1. **No offline/cache mode** — if the gateway drops, the UI goes blank. Consider
   a reconnect-with-state-preservation flow.
2. **No pagination on large datasets** — sessions and logs could grow unbounded.
   `logs.tail` has a cursor, but UI could be smarter about buffering.
3. **Config editor is raw JSON** — schema-validated form editing would be safer.
4. **No project/namespace view** — agents and sessions aren't grouped by project.
   Once `projects/index.yaml` is consumed by the gateway, this can be added.
5. **localStorage secrets** — URL and token are stored in localStorage. Consider
   warning users about shared-device risk.

---

## Next Steps

- [ ] **Project Management view** — show `projects/index.yaml` contents, let operators
      see which agents/workflows belong to each project
- [ ] **Agent collaboration graph** — visual map of agent relationships and handoffs
- [ ] **Policy editor** — structured YAML editor for agent tool policies, not raw text
- [ ] **Live event stream** — filterable real-time feed of all gateway events
- [ ] **Hook inspector** — view configured hooks, last invocations, failure history
- [ ] **Memory inspector** — browse agent memory entries, search, edit, delete
- [ ] **Audit trail view** — immutable log of all operator actions taken via Mission Control
- [ ] **Mobile-responsive layout** — current layout is desktop-optimized
