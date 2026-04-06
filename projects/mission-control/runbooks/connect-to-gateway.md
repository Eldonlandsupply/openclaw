# Runbook: Connect Mission Control to Gateway

**Trigger:** Operator wants to connect Mission Control to an OpenClaw gateway instance.  
**Expected outcome:** Green status indicator, all views load data.

## Prerequisites

- OpenClaw gateway running and reachable
- Gateway URL (default: `ws://127.0.0.1:18789`)
- Auth token (from gateway config, or left blank if no auth configured)
- Password (if gateway requires password auth; leave blank if not)

## Steps

1. Open `mission-control/index.html` in a browser (or navigate to hosted URL)
2. In the connection panel (top of page):
   - Enter **Gateway URL**: e.g. `ws://127.0.0.1:18789`
   - Enter **Token** if your gateway has `auth.token` configured
   - Enter **Password** if your gateway has `auth.password` configured
3. Click **Connect**
4. Confirm status dot turns green and status label shows "CONNECTED"
5. Navigate to **Overview** to verify snapshot data loads

## Troubleshooting

| Symptom                       | Likely Cause                             | Fix                                 |
| ----------------------------- | ---------------------------------------- | ----------------------------------- |
| Red dot, "connection refused" | Gateway not running                      | `openclaw gateway` or check systemd |
| Auth error                    | Wrong token/password                     | Check `config.yaml` `auth` section  |
| TLS error                     | Mixing ws:// and wss://                  | Use `wss://` for TLS gateways       |
| Empty agents list             | Gateway running but no agents configured | Use Agents view to create one       |
| CORS error                    | Browser security policy                  | Serve MC via HTTP, not file://      |

## Notes

- URL and token are stored in `localStorage` for convenience
- Password is **never** stored; re-enter on each session
- For remote gateways, use `wss://hostname:18789`
