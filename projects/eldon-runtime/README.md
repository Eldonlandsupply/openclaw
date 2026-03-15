# Eldon Land Supply OpenClaw Runtime

**Canonical project home:** `projects/eldon-runtime/`  
**Source files:** `eldon/` (repo root)  
**Status:** Active — Production  
**Owner:** Eldonlandsupply  
**Deployment:** Raspberry Pi at Eldon Land Supply, systemd service `openclaw.service`  

---

## What This Project Does

This is the bespoke Python agent runtime that runs 24/7 at Eldon Land Supply.
It is not the upstream TypeScript openclaw — it is a custom orchestration layer
built on top of the OpenClaw concepts, deployed on a Raspberry Pi, and wired
to the actual business communication channels and systems.

**Channels:** Telegram, Gmail, Outlook  
**Actions:** Top 100 business automation actions, risk-gated  
**Integrations:** Attio CRM  
**Memory:** Semantic search with ChromaDB/FAISS  

---

## Why It Exists

Eldon Land Supply needed a persistent AI automation layer that could handle
business communication in real-time, route requests through a controlled action
pipeline, and integrate with the CRM and document systems already in use.
The upstream TypeScript openclaw provides the gateway and agent protocol; this
Python runtime implements the Eldon-specific orchestration on top.

---

## What Systems It Touches

| System | How |
|--------|-----|
| Telegram | Bot API via telegram connector |
| Gmail | Gmail connector with OAuth |
| Outlook | Outlook connector via MSAL |
| Attio CRM | REST API via `eldon/src/openclaw/integrations/attio/` |
| OpenClaw Gateway | Optional; runtime can run standalone |
| systemd (Pi) | `eldon/deploy/systemd/openclaw.service` |

---

## How to Run It

### On the Raspberry Pi (production)
```bash
# Status
sudo systemctl status openclaw

# Start / Stop / Restart
sudo systemctl start openclaw
sudo systemctl stop openclaw
sudo systemctl restart openclaw

# View logs
journalctl -u openclaw -f
```

### Local development
```bash
cd eldon
cp config/env.example .env
# Edit .env with real credentials
pip install -r config/requirements.txt
python -m src.openclaw.main
```

### Pi bootstrap (first-time)
```bash
bash eldon/scripts/pi/bootstrap.sh
bash eldon/scripts/pi/install.sh
bash eldon/scripts/pi/install_service.sh
```

---

## Authoritative Files

| File | Purpose |
|------|---------|
| `eldon/src/openclaw/main.py` | Entry point |
| `eldon/src/openclaw/config.py` | Configuration loader |
| `eldon/config/config.yaml` | Runtime config (committed template) |
| `eldon/config/env.example` | Environment variable template |
| `eldon/action_allowlist/config.yaml` | Top 100 action allowlist governance |
| `eldon/gateway/app/gateway/pipeline.py` | Request pipeline |
| `eldon/gateway/app/gateway/risk.py` | Risk scoring engine |
| `eldon/memory-system/` | Semantic memory subsystem |
| `eldon/docs/operations.md` | Operations runbook |
| `eldon/scripts/doctor.py` | Health diagnostic tool |

---

## Common Operations

```bash
# Run health check
python eldon/scripts/doctor.py

# Validate config
cd eldon && make -C config validate

# Run tests
cd eldon && python -m pytest tests/

# Check action allowlist
python eldon/action_allowlist/scripts/validate_actions.py
```

---

## Risks and Open Questions

1. **Single Pi deployment** — no redundancy. If the Pi fails, the service stops.
2. **Secrets in .env** — rotated manually. No secrets manager integration.
3. **Memory store not backed up** — ChromaDB/FAISS data in `/opt/openclaw/data/` 
   should be backed up on a schedule.
4. **Action allowlist governance** — new actions require manual audit and scoring
   before inclusion. Process is documented but not enforced by CI.
5. **No circuit breaker** — if Attio or Telegram API is down, retries could pile up.

---

## Next Steps

- [ ] Add Pi backup cron for `/opt/openclaw/data/`
- [ ] Add Telegram/Gmail/Outlook health check to `doctor.py`
- [ ] Implement circuit breaker in connector layer
- [ ] Connect runtime status to Mission Control via gateway
- [ ] Document action allowlist review SLA
