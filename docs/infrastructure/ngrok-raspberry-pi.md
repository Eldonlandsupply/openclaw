---
summary: "Canonical ngrok standard for Raspberry Pi OpenClaw deployments"
read_when:
  - Exposing a Raspberry Pi hosted Gateway or operator service through ngrok
  - Installing durable remote access on OpenClaw nodes after reboot
  - Operating remote access without committing ngrok secrets
title: "ngrok on Raspberry Pi"
---

# ngrok on Raspberry Pi

Use this page as the canonical OpenClaw standard for running ngrok on Raspberry Pi and other ARM Linux hosts.

This standard is for controlled operator access to a local OpenClaw service, not for broad public exposure. Keep the Gateway loopback-bound, expose only the smallest required surface, and prefer reserved endpoints plus IP restrictions for sensitive access.

## When to use ngrok

Use ngrok on a Raspberry Pi when you need one of these outcomes:

- Stable remote access to an OpenClaw Gateway hosted on a Pi.
- Short-lived HTTP exposure for setup, diagnostics, or controlled operator use.
- Controlled SSH access when Tailscale or direct VPN access is unavailable.
- Reboot-safe tunnel startup via ngrok service mode.

Do not use ngrok when a safer or simpler option already exists:

- Use [Tailscale](/gateway/tailscale) first for tailnet-only access.
- Use [SSH forwarding](/gateway/remote) when you only need a one-off operator session.
- Do not expose admin panels, shell access, internal APIs, or health endpoints unless the operator explicitly needs them.

## OpenClaw defaults

- Keep the OpenClaw Gateway on `127.0.0.1:18789`.
- Use HTTP/HTTPS endpoints for the Gateway Control UI and WebSocket.
- Use TCP only for SSH or another protocol that cannot terminate over HTTP.
- Separate development tunnels from production tunnels with different endpoint names and, ideally, different ngrok accounts or reserved addresses.

## Files in this repo

- Canonical template: `config/ngrok/ngrok.template.yml`
- HTTP endpoint example: `config/ngrok/endpoints/http-service.template.yml`
- TCP SSH endpoint example: `config/ngrok/endpoints/tcp-ssh.template.yml`
- IP restriction example: `config/ngrok/policies/restrict-ips.template.yml`
- Install script: `scripts/ngrok/install_rpi.sh`
- Local config bootstrap: `scripts/ngrok/configure.sh`
- HTTP start helper: `scripts/ngrok/start_http_tunnel.sh`
- TCP SSH helper: `scripts/ngrok/start_tcp_ssh_tunnel.sh`
- Service install helper: `scripts/ngrok/install_service.sh`
- Status helper: `scripts/ngrok/status.sh`
- Validation helper: `scripts/ngrok/validate.sh`

## Prerequisites

- Raspberry Pi OS or another Linux distribution with `bash`, `curl`, `tar`, and `sudo`.
- OpenClaw or another local service already bound on the Pi.
- An ngrok account and authtoken from the ngrok dashboard.
- A decision on which local port you actually need to expose.

## Install flow

OpenClaw includes a script-first installation flow for Raspberry Pi.

### Recommended path

```bash
scripts/ngrok/install_rpi.sh
export NGROK_AUTHTOKEN='replace-me'
scripts/ngrok/configure.sh
scripts/ngrok/validate.sh
```

### Install method notes

- `scripts/ngrok/install_rpi.sh` defaults to archive installation so operators can place the binary in `/usr/local/bin` without relying on an APT image state.
- Set `NGROK_INSTALL_METHOD=apt` if you want the same APT flow shown on the current ngrok Raspberry Pi download page.
- Set `NGROK_ARCHIVE_URL=...` if ngrok changes archive URLs and you need to override the built-in mapping.

## Auth flow

Never commit a real authtoken.

Use one of these local-only patterns:

1. Export the token just for the current shell.
2. Store it in `~/.openclaw/.env` or a repo-local `.env` that stays ignored.
3. Generate `~/.config/ngrok/ngrok.yml` locally from the repo template, then let `ngrok config add-authtoken` or `ngrok authtoken` write the live secret.

Example local env entry:

```bash
NGROK_AUTHTOKEN=replace-with-dashboard-token
OPENCLAW_TUNNEL_PORT=18789
OPENCLAW_NGROK_DOMAIN=
OPENCLAW_NGROK_TCP_ADDRESS=
```

## HTTP tunnel patterns

Use HTTP for web apps, dashboards, APIs, and the OpenClaw Gateway control surface.

Common local ports on Raspberry Pi deployments include `3000`, `5000`, `8000`, `8080`, and OpenClaw's default `18789`. These are examples only. Validate the real upstream before exposing anything.

### Quick start for a local service

```bash
OPENCLAW_TUNNEL_PORT=18789 scripts/ngrok/start_http_tunnel.sh
```

### With a reserved domain

```bash
OPENCLAW_TUNNEL_PORT=18789 \
OPENCLAW_NGROK_DOMAIN='https://gateway-example.ngrok.app' \
OPENCLAW_ENABLE_IP_RESTRICTIONS=1 \
NGROK_TRAFFIC_POLICY_FILE='config/ngrok/policies/restrict-ips.template.yml' \
  scripts/ngrok/start_http_tunnel.sh
```

Use a reserved domain when you need stable reconnect behavior, durable bookmarks, or a fixed endpoint that service mode can restart after reboot.

## SSH over ngrok

Use TCP only for SSH or another raw TCP protocol.

### Appropriate use

- Emergency remote recovery when VPN or tailnet access is unavailable.
- Temporary break-glass admin access to a Pi.
- Controlled remote operator access to a lab device.

### Not appropriate

- Permanent default admin exposure.
- Shared shell access for multiple people.
- Public shell exposure without IP restrictions and account hardening.

### Start a TCP SSH tunnel

```bash
scripts/ngrok/start_tcp_ssh_tunnel.sh
```

This defaults to `22`. Override with `OPENCLAW_SSH_PORT` if the device uses another local SSH port.

Reserved TCP addresses are the preferred production option because they preserve a stable address for reboot-safe reconnects. Plan availability can vary by ngrok account tier and payment configuration, so operators need to confirm account eligibility before depending on them.

## Persistent startup after reboot

OpenClaw standardizes on config-driven service mode for durable Raspberry Pi access.

### Install service mode

```bash
scripts/ngrok/install_service.sh
scripts/ngrok/status.sh
```

Recommended service-mode pattern:

1. Generate `~/.config/ngrok/ngrok.yml` locally.
2. Keep endpoint definitions in the config file.
3. Install ngrok service mode against that config file.
4. Reboot the Pi and verify tunnel recovery with `scripts/ngrok/status.sh`.

## IP restriction and exposure controls

For sensitive services, add IP restrictions and reserved endpoints.

### HTTP restrictions

The included policy template shows ngrok `restrict-ips` usage. Copy it to a local-only file and replace the example CIDRs before using it.

### TCP restrictions

Reserved TCP addresses are the preferred stable transport for SSH. Apply account-level or endpoint-level access restrictions in the ngrok dashboard or API before treating the tunnel as production-safe.

## Agent operating procedure

### Start

```bash
scripts/ngrok/validate.sh
OPENCLAW_TUNNEL_PORT=18789 scripts/ngrok/start_http_tunnel.sh
```

### Stop

If running interactively, stop with `Ctrl+C`.

If running as a service:

```bash
ngrok service stop
```

### Verify

```bash
scripts/ngrok/status.sh
scripts/ngrok/validate.sh
```

Validation should confirm:

- `ngrok` is in `PATH`
- `ngrok version` returns successfully
- a local config file exists
- an authtoken is configured
- `ngrok config check` passes
- the target local port is already listening
- service mode can report status, if installed

## Failure recovery

### Missing token

Re-export `NGROK_AUTHTOKEN` and rerun:

```bash
scripts/ngrok/configure.sh
```

### Port is not listening

Start or fix the local app first, then retry:

```bash
ss -ltn
scripts/ngrok/validate.sh
```

### Service does not survive reboot

Re-run service install, then reboot and re-check:

```bash
scripts/ngrok/install_service.sh
sudo reboot
```

### Tunnel URL changes unexpectedly

You are likely using an ephemeral endpoint. Reserve the domain or TCP address in ngrok, update the local config, and reinstall the service if required.

## Security checklist

- Never commit `NGROK_AUTHTOKEN`.
- Never commit a live `ngrok.yml` that contains `agent.authtoken`.
- Keep OpenClaw loopback-bound on the Pi.
- Use only the minimum required protocol and port.
- Prefer short-lived operator tunnels for development.
- Prefer reserved endpoints plus IP restrictions for production.
- Do not expose shells, dashboards, config editors, or internal APIs unless there is a specific operator need.

## Related docs

- [Remote access](/operations/remote-access)
- [Gateway remote access](/gateway/remote)
- [Tailscale](/gateway/tailscale)
- [Raspberry Pi platform guide](/platforms/raspberry-pi)
