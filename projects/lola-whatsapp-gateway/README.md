# Lola WhatsApp Gateway Implementation Plan

**Canonical project home:** `projects/lola-whatsapp-gateway/`  
**Target repo:** `Eldonlandsupply/openclaw`  
**Status:** Proposed  
**Owner:** Eldonlandsupply  
**Deployment target:** Raspberry Pi, Docker, or systemd-managed Linux host

## Single biggest risk

The user-provided layout is Python-first, but this repository is TypeScript-first and already ships a WhatsApp channel plugin. Shipping a parallel Python stack inside this repo would split runtime patterns, config handling, and test tooling unless the boundary is explicit from day one.

## Best path forward

Build Lola as a self-contained Python project surface inside the repo, but keep the integration seam narrow:

1. **Keep Python isolated** under `openclaw/agents/lola` and `openclaw/apps/lola_whatsapp_gateway`.
2. **Treat WhatsApp ingress as an adapter**, not a second orchestration stack.
3. **Define stable contracts first** for normalized inbound events, auth checks, dedupe keys, and router outputs.

## Repo-ready target layout

```text
openclaw/
  agents/
    lola/
      __init__.py
      agent.py
      prompts.py
      router.py
      schemas.py
  apps/
    lola_whatsapp_gateway/
      __init__.py
      main.py
      routes.py
      provider_twilio.py
      provider_meta.py
      auth.py
      normalize.py
      dedupe.py
      outbound.py
      config.py
  configs/
    lola.example.env
  scripts/
    install_pi.sh
    run_lola_gateway.sh
    test_webhook_local.sh
  systemd/
    lola-whatsapp-gateway.service
  docker/
    lola-whatsapp-gateway.Dockerfile
  tests/
    test_lola_whatsapp_normalize.py
    test_lola_whatsapp_auth.py
    test_lola_whatsapp_dedupe.py
    test_lola_router.py
```

## Execution path

API, repo edit, CLI. Browser rejected because this is a repo-structure planning task and no UI validation was required.

## File-by-file plan

### `openclaw/agents/lola/`

- `agent.py`, create the Lola runtime entrypoint that accepts a normalized inbound message object and returns a typed response envelope.
- `prompts.py`, store system prompt builders and guardrail text only. No transport logic.
- `router.py`, map normalized inbound events to Lola actions, fallbacks, and escalation rules.
- `schemas.py`, define the shared dataclasses or Pydantic models used by both the agent and the gateway.

### `openclaw/apps/lola_whatsapp_gateway/`

- `main.py`, expose the ASGI app and bootstrap config.
- `routes.py`, define health, webhook, and outbound endpoints.
- `provider_twilio.py`, verify Twilio signatures and map Twilio payloads into normalized schemas.
- `provider_meta.py`, verify Meta webhook payloads and map them into normalized schemas.
- `auth.py`, centralize webhook auth checks and reject unsigned or malformed requests loudly.
- `normalize.py`, convert provider-specific payloads into one inbound event schema.
- `dedupe.py`, generate deterministic idempotency keys from provider message IDs and cache timestamps.
- `outbound.py`, translate Lola replies into Twilio or Meta outbound API calls.
- `config.py`, load environment variables once, validate them, and expose typed config.

### Ops and packaging

- `configs/lola.example.env`, define every required environment variable with placeholders only.
- `scripts/install_pi.sh`, install Python, venv, dependencies, env file, and service unit with `set -euo pipefail`.
- `scripts/run_lola_gateway.sh`, run the gateway locally with explicit host, port, and config path.
- `scripts/test_webhook_local.sh`, send a deterministic sample webhook into localhost for smoke testing.
- `systemd/lola-whatsapp-gateway.service`, manage the gateway on Raspberry Pi with restart policy and explicit working directory.
- `docker/lola-whatsapp-gateway.Dockerfile`, build a minimal image for reproducible deploys.

### Tests

- `test_lola_whatsapp_normalize.py`, cover Twilio and Meta payload normalization edge cases.
- `test_lola_whatsapp_auth.py`, cover valid signatures, invalid signatures, missing headers, and stale timestamps.
- `test_lola_whatsapp_dedupe.py`, cover replay detection and provider-specific message IDs.
- `test_lola_router.py`, cover router decisions, fallback behavior, and escalation.

## Implementation phases

### Phase 1, contracts first

Acceptance criteria:

- One normalized inbound event schema exists.
- One outbound reply schema exists.
- Both Twilio and Meta adapters target the same schema.
- Router inputs and outputs are type-checked.

Deliverables:

- `schemas.py`
- `normalize.py`
- `router.py`
- `test_lola_whatsapp_normalize.py`
- `test_lola_router.py`

### Phase 2, provider ingress and auth

Acceptance criteria:

- Twilio signature verification is mandatory when Twilio mode is enabled.
- Meta verification token and signature validation are mandatory when Meta mode is enabled.
- Health endpoint reports provider mode and config completeness without exposing secrets.
- Replay attempts are rejected or no-op'd deterministically.

Deliverables:

- `provider_twilio.py`
- `provider_meta.py`
- `auth.py`
- `dedupe.py`
- `routes.py`
- `test_lola_whatsapp_auth.py`
- `test_lola_whatsapp_dedupe.py`

### Phase 3, runtime and deployability

Acceptance criteria:

- ASGI app starts with a single documented command.
- Example env file matches runtime config exactly.
- Pi install script and systemd unit can run the service without manual edits beyond env values.
- Docker build succeeds and starts the same app entrypoint.

Deliverables:

- `main.py`
- `config.py`
- `configs/lola.example.env`
- `scripts/install_pi.sh`
- `scripts/run_lola_gateway.sh`
- `scripts/test_webhook_local.sh`
- `systemd/lola-whatsapp-gateway.service`
- `docker/lola-whatsapp-gateway.Dockerfile`

## Security checklist

- Reject absolute paths, `..`, and symlink escapes for any file write location.
- Do not accept unsigned inbound webhooks.
- Do not log secrets, raw auth headers, or full customer payloads.
- Use deterministic dedupe keys to prevent provider retries from double-processing.
- Keep outbound provider credentials separate from inbound verification secrets.
- Fail loudly on missing config. No silent fallback to insecure defaults.

## Unknowns

- UNKNOWN, whether Twilio, Meta, or both must be supported on day one.
- UNKNOWN, whether Lola runs local inference, remote API calls, or delegates into existing OpenClaw services.
- UNKNOWN, which store backs dedupe state on Raspberry Pi, memory-only cache, sqlite, or redis.
- UNKNOWN, whether outbound media, templates, or interactive messages are in scope.

## Recommended default assumptions

Use these unless product requirements say otherwise:

- Provider mode starts with **Twilio first**, Meta second.
- Runtime uses **FastAPI + Uvicorn**.
- Schemas use **Pydantic v2**.
- Dedupe store uses **sqlite** on Pi for crash-safe idempotency.
- Router returns plain text first, media later.

## Smoke-check repro block

```bash
set -euo pipefail

python -m pytest tests/test_lola_whatsapp_normalize.py tests/test_lola_router.py
python -m pytest tests/test_lola_whatsapp_auth.py tests/test_lola_whatsapp_dedupe.py
python -m uvicorn openclaw.apps.lola_whatsapp_gateway.main:app --host 0.0.0.0 --port 8080
bash scripts/test_webhook_local.sh
```

Expected result:

- Tests pass.
- Health endpoint returns 200.
- Sample webhook returns 200 or 202.
- Duplicate webhook replay is ignored deterministically.

## Result

This plan is repo-ready, but only if the repo owners accept a mixed-language boundary. If they want tighter operational consistency, the better alternative is to keep the gateway in TypeScript and reserve Python for Lola-only inference components.
