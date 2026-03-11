# OpenClaw Pi Repair Runbook
## Eldon Land Supply — EldonOpenClaw Deployment
### Generated: 2026-03-11

---

## HOW TO USE THIS

1. Copy `openclaw_repair.sh` to the Raspberry Pi
2. Run it as your normal user (needs sudo)
3. Read the report it generates in `~/eldon/backups/openclaw_repair_*/`

```bash
# From your Mac — copy script to Pi
scp openclaw_repair.sh pi@<PI_IP>:~/

# SSH in
ssh pi@<PI_IP>

# Make executable and run
chmod +x ~/openclaw_repair.sh
sudo bash ~/openclaw_repair.sh 2>&1 | tee ~/repair_run.log
```

The script is non-destructive first — it backs up before changing anything.

---

## WHAT THE SCRIPT DOES (PHASE BY PHASE)

### Phase 1 — Forensic Discovery
Scans for every OpenClaw trace on the machine:
- Running processes, systemd units, cron jobs
- All repo clones, venvs, .env files
- tmux/screen sessions, nohup outputs
- Log directories, bash history references

### Phase 2 — Repo Truth Test
For every found repo clone:
- Records remote URL, branch, git status, HEAD commit
- Backs up any uncommitted changes to timestamped rescue folder
- Determines which clone is canonical

### Phase 3 — Config Discovery
Maps all config and .env files found. Records present/missing keys.

### Phase 4–6 — Deployment Repair
- Creates canonical deployment at `/opt/openclaw`
- Creates `openclaw` system user if missing
- Clones or pulls from `Eldonlandsupply/openclaw` via authenticated HTTPS
- Builds clean venv with Python 3.11+
- Installs from `pyproject.toml` (falls back to `requirements.txt`)
- Creates `/etc/openclaw/openclaw.env` with correct permissions (600)
- Detects entrypoint automatically
- Writes clean systemd unit file

### Phase 7 — Legacy Conflict Removal
- Disables any other openclaw-named systemd services
- Kills stray openclaw Python processes
- Comments out openclaw cron entries (with backup)

### Phase 8 — Service Activation
- `systemctl daemon-reload`
- `systemctl enable openclaw` (boot persistence)
- `systemctl start openclaw`

### Phase 9 — Verification
- `systemctl status`
- `journalctl` last 30 lines
- Process list check
- Restart test
- Duplicate process check
- Core import sanity test
- `scripts/doctor.py` run

---

## CANONICAL DEPLOYMENT TARGETS

| Item | Path |
|---|---|
| Repo | `/opt/openclaw` |
| Virtualenv | `/opt/openclaw/.venv` |
| Env file | `/etc/openclaw/openclaw.env` |
| Service | `openclaw.service` |
| Unit file | `/etc/systemd/system/openclaw.service` |
| Data dir | `/var/lib/openclaw` |
| Backups | `~/eldon/backups/openclaw_repair_TIMESTAMP/` |

---

## ENV FILE — PRE-FILLED VALUES

The script will create `/etc/openclaw/openclaw.env` with:

```bash
OPENCLAW_CHAT_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=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
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENCLAW_ENV=production
OPENCLAW_LOG_LEVEL=info
OPENCLAW_CONNECTOR_CLI=true
OPENCLAW_CONNECTOR_TELEGRAM=false
OPENCLAW_CONNECTOR_VOICE=false
OPENCLAW_MEMORY_ENABLED=false
OPENCLAW_ACTION_CONFIRM=true
```

**Note:** This uses OpenRouter as the LLM backend. The `OPENAI_BASE_URL` override points to OpenRouter's OpenAI-compatible endpoint.

---

## MAINTENANCE COMMANDS

```bash
# Check status
sudo systemctl status openclaw

# Follow live logs
sudo journalctl -u openclaw -f

# Last 100 lines of logs
sudo journalctl -u openclaw -n 100 --no-pager

# Restart
sudo systemctl restart openclaw

# Stop
sudo systemctl stop openclaw

# Pull latest code and restart
cd /opt/openclaw
sudo git pull origin main
sudo systemctl restart openclaw

# Reload systemd after manual unit file edits
sudo systemctl daemon-reload
sudo systemctl restart openclaw

# Run doctor check manually
cd /opt/openclaw
sudo -u openclaw bash -c "source /etc/openclaw/openclaw.env; .venv/bin/python scripts/doctor.py"

# Edit env file
sudo nano /etc/openclaw/openclaw.env
sudo systemctl restart openclaw

# Check what's in the env file (keys only)
sudo grep -v "^#" /etc/openclaw/openclaw.env | cut -d= -f1
```

---

## OPEN ITEMS (REQUIRE YOUR ACTION)

1. **OpenRouter key** — Confirm `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` is still active. Check at https://openrouter.ai/keys

2. **GitHub PAT** — The token `github_pat_11BSV5OZY0FIZPITonMw8C_...` was used for cloning. Bake a fresh PAT with Contents: Read scope if you want the Pi to pull updates. Revoke the old one if it was exposed in chat.

3. **Telegram** — If you want the Telegram connector, set `TELEGRAM_BOT_TOKEN` in `/etc/openclaw/openclaw.env` and set `OPENCLAW_CONNECTOR_TELEGRAM=true`.

4. **Memory** — If memory/vector features are needed: set `OPENCLAW_EMBED_MODEL=text-embedding-3-small` and `OPENCLAW_MEMORY_ENABLED=true` in the env file.

5. **Azure AD secret** — The client secret `2acf5611-26fd-4620-907b-bcaffd8d20c6` for the Outlook connector — confirm it's still valid in the Azure portal under App Registrations → Openclaw → Certificates & Secrets.

6. **connectors/memory/actions src directories** — Per the README, these modules are not yet implemented. The runtime will start but only CLI connector is functional.

---

## IF THE SCRIPT FAILS

The script is designed to continue through failures. If it hard-stops:

1. Check `~/eldon/backups/openclaw_repair_*/repair.log` for the last successful step
2. All backups are in that same timestamped folder
3. The unit file will be in place even if the service didn't start
4. Minimum viable next step: fix the blocker listed in OPEN ITEMS and run `sudo systemctl start openclaw`

---

## SYSTEMD UNIT (for reference)

```ini
[Unit]
Description=OpenClaw Agent Runtime
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=openclaw
Group=openclaw
WorkingDirectory=/opt/openclaw
EnvironmentFile=/etc/openclaw/openclaw.env
ExecStart=/opt/openclaw/.venv/bin/python -m openclaw.main /opt/openclaw/config.yaml
Restart=always
RestartSec=5
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=openclaw
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/openclaw /opt/openclaw/.data

[Install]
WantedBy=multi-user.target
```
