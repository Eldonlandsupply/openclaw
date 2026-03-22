# OpenClaw Mission Control

Production-grade operator interface for the OpenClaw agent fleet.

## Usage

1. Open `index.html` in your browser
2. Enter your gateway WebSocket URL (default: `ws://localhost:18789`)
3. Enter your gateway auth token (or leave blank for local connections)
4. Click **Connect**

Or click **Demo Mode** to explore the UI without a running gateway.

## ngrok note

Mission Control does not need its own ngrok endpoint in normal OpenClaw deployments. Tunnel the OpenClaw Gateway instead, then connect Mission Control to that `wss://` endpoint. Use `docs/infrastructure/ngrok-raspberry-pi.md` as the canonical runbook.

## Features

- **Fleet Overview** — all agents, status, audit trail
- **Agent Detail** — identity, model config, file editor, tools policy, cron, guardrails
- **Core Files Editor** — edit SOUL.md, IDENTITY.md, TOOLS.md, AGENTS.md inline
- **Tool Access Policy** — per-tool toggle matrix with profile presets
- **Cron Jobs** — per-agent scheduled task management
- **Governance Panel** — approval requirements, sandbox mode, blocked actions, collaboration scope
- **Topology View** — collaboration graph with communication policy inspection
- **Fleet Cron** — all scheduled jobs across the fleet
- **Create Agent** — guided wizard calling `agents.create` gateway method

## Gateway Methods Used

| Method | Description |
|---|---|
| `connect` | WebSocket handshake with auth token |
| `agents.list` | List all configured agents |
| `agents.create` | Create new agent with workspace |
| `agents.update` | Update agent name/model |
| `agents.files.list` | List agent workspace files |
| `agents.files.get` | Read a specific agent file |
| `agents.files.set` | Write/update an agent file |

## Architecture

- Standalone HTML — no build step, no dependencies to install
- React 18 via CDN
- Connects directly to OpenClaw gateway WebSocket (`ws://` or `wss://`)
- Gateway protocol: JSON request/response with `seq`-based correlation
- Auth: `connect.params.auth.token` in the handshake

## Design

- Dark, minimal, operationally serious
- JetBrains Mono + Syne typefaces
- Red accent (`#e84c3d`) — OpenClaw brand
- Rail → Sidebar → Main content layout
- No toy dashboard energy
