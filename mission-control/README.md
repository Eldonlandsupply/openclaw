# OpenClaw Mission Control

Standalone web-based operational control plane for the OpenClaw agent ecosystem.

**No build step. No dependencies. No framework.**  
Open `index.html` directly in a browser — or serve the directory with any static server.

---

## What it is

Mission Control is a single-page HTML/CSS/JS app that connects directly to the OpenClaw
gateway via WebSocket. It speaks the native OpenClaw gateway protocol (request/response frames,
real-time events) to give you a full operational interface.

---

## Usage

### Option 1 — Open directly

```bash
open mission-control/index.html
```

Enter your gateway URL (default `ws://127.0.0.1:18789`), token, and password as needed.

### Option 2 — Static server

```bash
cd mission-control
python3 -m http.server 8080
# open http://localhost:8080
```

### Option 3 — From Docker / VPS

If your OpenClaw gateway is running on a remote host, use:

```
ws://your-host:18789
```

For TLS-secured gateways: `wss://your-host:18789`

If the gateway is hosted on a Raspberry Pi behind ngrok, expose the Gateway endpoint, not the static Mission Control files. Follow the canonical guide at `docs/infrastructure/ngrok-raspberry-pi.md`. Mission Control only needs the resulting `wss://` URL plus the normal gateway token or password.

---

## Features

| View         | What it does                                                     |
| ------------ | ---------------------------------------------------------------- |
| **Overview** | Live gateway snapshot: uptime, connected clients, agent count    |
| **Agents**   | Create, edit, delete agents; browse and edit agent files         |
| **Sessions** | Browse sessions with search, preview transcripts, reset/delete   |
| **Channels** | Live status of all configured channel integrations               |
| **Cron**     | View, trigger, and remove scheduled jobs                         |
| **Models**   | All available models from configured providers                   |
| **Config**   | Live config editor — get, edit, and save the gateway config JSON |
| **Logs**     | Real-time log tail with follow mode                              |
| **Nodes**    | Paired remote nodes overview                                     |

---

## Protocol

Mission Control speaks the standard OpenClaw Gateway WebSocket protocol.  
All operations use typed request/response frames (`type: "request"` / `type: "response"`).

Key commands used:

- `connect` — handshake and auth
- `agents.list`, `agents.create`, `agents.update`, `agents.delete`
- `agents.files.list`, `agents.files.get`, `agents.files.set`
- `sessions.list`, `sessions.preview`, `sessions.reset`, `sessions.delete`
- `channels.status`
- `cron.list`, `cron.add`, `cron.run`, `cron.remove`
- `models.list`
- `config.get`, `config.set`
- `logs.tail`
- `nodes.list`
- `snapshot`

---

## Files

```
mission-control/
├── index.html   — Shell layout and DOM structure
├── mc.css       — Design system + component styles
├── mc.js        — Gateway client + all view logic
└── README.md    — This file
```

---

## Security

- Credentials are stored in `localStorage` for convenience (URL and token only — password is never stored).
- All connections are direct browser-to-gateway WebSocket. No proxy, no backend.
- For remote deployments, use `wss://` and ensure your gateway has TLS configured.
