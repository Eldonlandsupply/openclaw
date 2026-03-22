---
summary: "Operator decision guide for remote access across SSH, Tailscale, and ngrok"
read_when:
  - Choosing how to access OpenClaw remotely
  - Hardening Raspberry Pi or remote Gateway access
  - Deciding whether ngrok should be used at all
title: "Remote access"
---

# Remote access

This page is the operator decision guide for remote access across OpenClaw.

## Preferred order

Choose the narrowest remote-access path that satisfies the job:

1. Loopback-only Gateway with [SSH forwarding](/gateway/remote)
2. [Tailscale](/gateway/tailscale) for tailnet-only access
3. ngrok for controlled exposure when the first two options are unavailable or operationally weaker for the specific deployment

## When ngrok is justified

Use ngrok when you need one of these conditions:

- A Raspberry Pi must stay reachable after reboot without manual SSH forwarding.
- The operator needs a stable remote URL or reserved TCP address.
- The device is outside a tailnet and direct inbound networking is not practical.
- A short-lived support window needs audited, deterministic start and stop steps.

## When ngrok is the wrong choice

Do not default to ngrok for these cases:

- Routine operator access where SSH port forwarding already works.
- Tailnet-only deployments where Tailscale Serve is already in place.
- Public exposure of dashboards, admin routes, or shell access without a hard operator requirement.

## Protocol selection

| Use case                        | Protocol           | Notes                                                                                                                               |
| ------------------------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| OpenClaw Gateway UI + WebSocket | HTTP or HTTPS      | Preferred. Keep local upstream on `127.0.0.1:18789`.                                                                                |
| Mission Control static UI       | No tunnel required | Mission Control is static. Tunnel the Gateway, not the static files, unless a remote operator specifically needs the static server. |
| SSH recovery access             | TCP                | Use only with explicit warnings, account hardening, and IP restrictions or reserved addresses.                                      |
| Internal health checks          | Usually none       | Prefer local checks, SSH, or tailnet access over public exposure.                                                                   |

## Raspberry Pi standard

For Raspberry Pi devices, use the canonical runbook:

- [ngrok on Raspberry Pi](/infrastructure/ngrok-raspberry-pi)

That document defines:

- install and auth flow
- config templates
- start and stop scripts
- validation checks
- service-mode persistence
- recovery after reboot
- exposure controls for HTTP and SSH

## OpenClaw-specific guidance

- Tunnel the Gateway endpoint, not every subproject.
- Keep agent-facing and operator-facing services separate.
- Treat Mission Control, dashboards, config editors, and shell access as high-sensitivity surfaces.
- If a subproject does not need outside access, do not add an ngrok endpoint for it.

## Quick operator commands

```bash
scripts/ngrok/install_rpi.sh
scripts/ngrok/configure.sh
scripts/ngrok/validate.sh
OPENCLAW_TUNNEL_PORT=18789 scripts/ngrok/start_http_tunnel.sh
scripts/ngrok/install_service.sh
scripts/ngrok/status.sh
```

## Related docs

- [Gateway remote access](/gateway/remote)
- [Tailscale](/gateway/tailscale)
- [Raspberry Pi platform guide](/platforms/raspberry-pi)
