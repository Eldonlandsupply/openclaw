#!/usr/bin/env bash
# ============================================================
# OpenClaw Raspberry Pi — Forensic Audit & Repair Script
# Version: 1.0  |  Target: EldonOpenClaw on arm64 Raspberry Pi
# Run as: the pi user (sudo available)
# ============================================================
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT="$HOME/eldon/backups/openclaw_repair_${TIMESTAMP}"
LOG="$BACKUP_ROOT/repair.log"
REPORT="$BACKUP_ROOT/repair_report_${TIMESTAMP}.txt"

CANONICAL_PATH="/opt/openclaw"
CANONICAL_VENV="$CANONICAL_PATH/.venv"
CANONICAL_ENV="/etc/openclaw/openclaw.env"
CANONICAL_SERVICE="openclaw"
CANONICAL_UNIT="/etc/systemd/system/openclaw.service"
REPO_URL="https://github.com/Eldonlandsupply/openclaw"
GITHUB_TOKEN="github_pat_11BSV5OZY0FIZPITonMw8C_JH7tgqkb8EWMPNN5pGmhGvBzVPcf3YPZc3PaDTuIUcqYG52F7KEnSneDAs"

# ── Helpers ────────────────────────────────────────────────
log()   { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
warn()  { echo "[WARN]  $*" | tee -a "$LOG"; }
step()  { echo; echo "══════════════════════════════════════════" | tee -a "$LOG"; echo "  $*" | tee -a "$LOG"; echo "══════════════════════════════════════════" | tee -a "$LOG"; echo; }
ok()    { echo "  ✓  $*" | tee -a "$LOG"; }
fail()  { echo "  ✗  $*" | tee -a "$LOG"; }
hr()    { echo "──────────────────────────────────────────" | tee -a "$LOG"; }

ensure_env_permissions() {
  local env_path="$1"
  # This must remain readable by the runtime user. If root rewrites this file
  # without restoring owner/mode, dotenv and EnvironmentFile reads fail and
  # connector flags silently fall back to defaults.
  sudo chown openclaw:openclaw "$env_path"
  sudo chmod 640 "$env_path"
  sudo -u openclaw test -r "$env_path" || {
    fail "openclaw user cannot read $env_path after ownership fix"
    exit 1
  }
}

write_env_atomic() {
  local target="$1"
  local tmp
  tmp=$(mktemp "${target}.tmp.XXXXXX")
  cat > "$tmp"
  sudo install -o openclaw -g openclaw -m 640 "$tmp" "$target"
  rm -f "$tmp"
}

# ── Setup backup directory ─────────────────────────────────
mkdir -p "$BACKUP_ROOT"
touch "$LOG"
log "Repair session started: $TIMESTAMP"
log "Backup root: $BACKUP_ROOT"

# ============================================================
# PHASE 1: FORENSIC DISCOVERY
# ============================================================
step "PHASE 1: FORENSIC DISCOVERY"

{
echo "========================================================"
echo " OpenClaw Repair Report — $TIMESTAMP"
echo "========================================================"
echo

echo "── MACHINE FACTS ────────────────────────────────────"
echo "hostname:     $(hostname)"
echo "uname:        $(uname -a)"
echo "os-release:"
cat /etc/os-release 2>/dev/null | head -6
echo "python3:      $(python3 --version 2>/dev/null || echo NOT FOUND)"
echo "which python3:$(which python3 2>/dev/null || echo NOT FOUND)"
echo "pip3:         $(pip3 --version 2>/dev/null || echo NOT FOUND)"
echo "git:          $(git --version 2>/dev/null || echo NOT FOUND)"
echo "systemd:      $(systemctl --version 2>/dev/null | head -1 || echo NOT FOUND)"
echo "uptime:       $(uptime)"
echo "disk:         $(df -h / | tail -1)"
echo "memory:       $(free -h | grep Mem)"
echo
} | tee -a "$LOG" >> "$REPORT"

log "Scanning for OpenClaw artifacts..."

{
echo "── OPENCLAW PROCESS SCAN ────────────────────────────"
ps aux | grep -i openclaw | grep -v grep || echo "(none running)"
echo

echo "── SYSTEMD UNIT SCAN ────────────────────────────────"
systemctl list-units --type=service --all 2>/dev/null | grep -i openclaw || echo "(no systemd units found)"
echo
find /etc/systemd/system /lib/systemd/system /usr/lib/systemd/system -iname "*openclaw*" 2>/dev/null || echo "(no unit files found)"
echo

echo "── CRON SCAN ────────────────────────────────────────"
crontab -l 2>/dev/null | grep -i openclaw || echo "(no openclaw cron entries)"
ls /etc/cron* 2>/dev/null | xargs grep -l openclaw 2>/dev/null || echo "(no system cron entries)"
echo

echo "── REPO SCAN ────────────────────────────────────────"
find "$HOME" /opt /srv /var -maxdepth 6 -iname "*openclaw*" -o -iname "EldonOpenClaw" 2>/dev/null | grep -v ".git/" | sort || echo "(none found)"
echo

echo "── VENV SCAN ────────────────────────────────────────"
find "$HOME" /opt -maxdepth 6 -name "pyvenv.cfg" 2>/dev/null | while read f; do
  dir=$(dirname "$f")
  echo "  venv: $dir"
  "$dir/bin/python" --version 2>/dev/null && echo "       (valid python)" || echo "       (broken)"
done
echo

echo "── .ENV FILE SCAN ───────────────────────────────────"
find "$HOME" /opt /etc -maxdepth 6 -name ".env" -o -name "openclaw.env" 2>/dev/null | sort || echo "(none found)"
echo

echo "── TMUX/SCREEN SCAN ─────────────────────────────────"
tmux ls 2>/dev/null || echo "(no tmux sessions)"
screen -ls 2>/dev/null || echo "(no screen sessions)"
echo

echo "── NOHUP SCAN ───────────────────────────────────────"
find "$HOME" /tmp -maxdepth 3 -name "nohup.out" 2>/dev/null | head -5 || echo "(none)"
echo

echo "── LOG DIRECTORIES ──────────────────────────────────"
find /var/log "$HOME" /opt -maxdepth 5 -iname "*openclaw*" -type f 2>/dev/null | head -20 || echo "(none)"
echo

echo "── BASH HISTORY SCAN ────────────────────────────────"
grep -i openclaw "$HOME/.bash_history" 2>/dev/null | tail -20 || echo "(none in bash history)"
grep -i openclaw "$HOME/.zsh_history" 2>/dev/null | tail -20 || echo "(none in zsh history)"
echo

} | tee -a "$LOG" >> "$REPORT"

# ============================================================
# PHASE 2: REPO TRUTH TEST
# ============================================================
step "PHASE 2: REPO TRUTH TEST"

CANDIDATE_REPOS=()
while IFS= read -r path; do
  if [ -d "$path/.git" ]; then
    CANDIDATE_REPOS+=("$path")
  fi
done < <(find "$HOME" /opt -maxdepth 6 -name ".git" -type d 2>/dev/null | sed 's|/.git$||' | grep -i openclaw)

{
echo "── REPO CANDIDATES ──────────────────────────────────"
if [ ${#CANDIDATE_REPOS[@]} -eq 0 ]; then
  echo "(no git repos found — fresh install required)"
else
  for repo in "${CANDIDATE_REPOS[@]}"; do
    echo "  path:   $repo"
    echo "  remote: $(git -C "$repo" remote -v 2>/dev/null | head -2 || echo NONE)"
    echo "  branch: $(git -C "$repo" branch --show-current 2>/dev/null || echo UNKNOWN)"
    echo "  status: $(git -C "$repo" status --short 2>/dev/null | head -5 || echo ERROR)"
    echo "  head:   $(git -C "$repo" log --oneline -1 2>/dev/null || echo NONE)"
    echo
  done
fi
} | tee -a "$LOG" >> "$REPORT"

# Backup uncommitted changes before touching anything
for repo in "${CANDIDATE_REPOS[@]}"; do
  if git -C "$repo" status --short 2>/dev/null | grep -q .; then
    RESCUE="$BACKUP_ROOT/repo_rescue_$(basename $repo)"
    mkdir -p "$RESCUE"
    git -C "$repo" diff > "$RESCUE/uncommitted.patch" 2>/dev/null || true
    git -C "$repo" stash list > "$RESCUE/stash_list.txt" 2>/dev/null || true
    cp -r "$repo/.env" "$RESCUE/" 2>/dev/null || true
    log "Backed up uncommitted changes from $repo to $RESCUE"
  fi
done

# ============================================================
# PHASE 3: CONFIG DISCOVERY
# ============================================================
step "PHASE 3: CONFIG DISCOVERY"

{
echo "── CONFIG FILES FOUND ───────────────────────────────"
find "$HOME" /opt /etc -maxdepth 6 \( -name "config.yaml" -o -name ".env" -o -name "openclaw.env" \) 2>/dev/null | sort | while read f; do
  echo "  $f"
done
echo

echo "── EXISTING .ENV CONTENTS (keys only, no values) ────"
find "$HOME" /opt /etc -maxdepth 6 -name ".env" -o -name "openclaw.env" 2>/dev/null | while read f; do
  echo "  $f:"
  grep -v "^#" "$f" 2>/dev/null | cut -d= -f1 | sed 's/^/    /' || true
done
echo
} | tee -a "$LOG" >> "$REPORT"

# ============================================================
# PHASE 4–6: DEPLOYMENT SETUP
# ============================================================
step "PHASE 4–6: CANONICAL DEPLOYMENT"

log "Creating canonical deployment at $CANONICAL_PATH ..."

# ── Stop existing service if running ──
if systemctl is-active --quiet openclaw 2>/dev/null; then
  log "Stopping existing openclaw service..."
  sudo systemctl stop openclaw || true
  echo "STOPPED existing openclaw service" >> "$REPORT"
fi

# ── Backup existing unit file ──
if [ -f "$CANONICAL_UNIT" ]; then
  cp "$CANONICAL_UNIT" "$BACKUP_ROOT/openclaw.service.bak"
  log "Backed up existing unit file"
fi

# ── Backup existing env file ──
if [ -f "$CANONICAL_ENV" ]; then
  cp "$CANONICAL_ENV" "$BACKUP_ROOT/openclaw.env.bak"
  log "Backed up existing env file"
fi

# ── Create dirs ──
sudo mkdir -p "$CANONICAL_PATH"
sudo mkdir -p /etc/openclaw
sudo mkdir -p /var/lib/openclaw
sudo mkdir -p /var/log/openclaw

# ── Ensure openclaw user exists ──
if ! id openclaw &>/dev/null; then
  sudo useradd --system --no-create-home --shell /usr/sbin/nologin openclaw
  log "Created openclaw system user"
fi

sudo chown openclaw:openclaw /var/lib/openclaw
sudo chown openclaw:openclaw /var/log/openclaw

# ── Clone or update repo ──
AUTHED_URL="https://${GITHUB_TOKEN}@github.com/Eldonlandsupply/openclaw"

if [ -d "$CANONICAL_PATH/.git" ]; then
  EXISTING_REMOTE=$(git -C "$CANONICAL_PATH" remote get-url origin 2>/dev/null | sed 's|https://[^@]*@||' || echo "")
  if echo "$EXISTING_REMOTE" | grep -qi "eldonlandsupply/openclaw"; then
    log "Existing repo found at $CANONICAL_PATH — pulling latest..."
    sudo git -C "$CANONICAL_PATH" fetch origin 2>&1 | tee -a "$LOG"
    sudo git -C "$CANONICAL_PATH" checkout main 2>&1 | tee -a "$LOG" || sudo git -C "$CANONICAL_PATH" checkout master 2>&1 | tee -a "$LOG"
    sudo git -C "$CANONICAL_PATH" pull origin HEAD 2>&1 | tee -a "$LOG"
    echo "REPO: Updated existing clone at $CANONICAL_PATH" >> "$REPORT"
  else
    warn "Unexpected remote at $CANONICAL_PATH — backing up and recloning"
    sudo cp -r "$CANONICAL_PATH" "$BACKUP_ROOT/canonical_path_old"
    sudo rm -rf "$CANONICAL_PATH"
    sudo git clone "$AUTHED_URL" "$CANONICAL_PATH" 2>&1 | tee -a "$LOG"
    echo "REPO: Recloned (bad remote) to $CANONICAL_PATH" >> "$REPORT"
  fi
else
  log "No repo at $CANONICAL_PATH — cloning fresh..."
  sudo git clone "$AUTHED_URL" "$CANONICAL_PATH" 2>&1 | tee -a "$LOG"
  echo "REPO: Fresh clone to $CANONICAL_PATH" >> "$REPORT"
fi

sudo chown -R openclaw:openclaw "$CANONICAL_PATH"

# ── Checkout main branch ──
BRANCH=$(git -C "$CANONICAL_PATH" branch --show-current 2>/dev/null || echo "unknown")
log "Active branch: $BRANCH"

# ── Build clean venv ──
log "Building virtual environment..."
if [ -d "$CANONICAL_VENV" ]; then
  # Test if it's healthy
  if "$CANONICAL_VENV/bin/python" -c "import sys; assert sys.version_info >= (3,11)" 2>/dev/null; then
    ok "Existing venv is healthy (Python $("$CANONICAL_VENV/bin/python" --version 2>/dev/null))"
  else
    warn "Existing venv broken — rebuilding"
    sudo rm -rf "$CANONICAL_VENV"
    sudo -u openclaw python3 -m venv "$CANONICAL_VENV"
  fi
else
  sudo -u openclaw python3 -m venv "$CANONICAL_VENV"
fi

log "Installing dependencies..."
sudo -u openclaw "$CANONICAL_VENV/bin/pip" install --upgrade pip --quiet 2>&1 | tee -a "$LOG"

# Install from pyproject.toml if it exists, otherwise requirements.txt
if [ -f "$CANONICAL_PATH/pyproject.toml" ]; then
  sudo -u openclaw "$CANONICAL_VENV/bin/pip" install -e "$CANONICAL_PATH[dev]" --quiet 2>&1 | tee -a "$LOG"
  ok "Installed via pyproject.toml"
elif [ -f "$CANONICAL_PATH/requirements.txt" ]; then
  sudo -u openclaw "$CANONICAL_VENV/bin/pip" install -r "$CANONICAL_PATH/requirements.txt" --quiet 2>&1 | tee -a "$LOG"
  ok "Installed via requirements.txt"
else
  warn "No pyproject.toml or requirements.txt found — installing core deps manually"
  sudo -u openclaw "$CANONICAL_VENV/bin/pip" install pydantic>=2.0 pydantic-settings>=2.0 pyyaml>=6.0 aiohttp>=3.9 python-dotenv>=1.0 --quiet 2>&1 | tee -a "$LOG"
fi

# ── Create env file ──
log "Checking env file at $CANONICAL_ENV..."

if [ ! -f "$CANONICAL_ENV" ]; then
  log "Creating $CANONICAL_ENV from .env.example..."

  # Find best .env source
  ENV_SOURCE=""
  for candidate in "$CANONICAL_PATH/.env" "$CANONICAL_PATH/.env.example" "$HOME/openclaw/.env" "$HOME/eldon/repos/openclaw/.env"; do
    if [ -f "$candidate" ]; then
      ENV_SOURCE="$candidate"
      break
    fi
  done

  if [ -n "$ENV_SOURCE" ] && [ "$ENV_SOURCE" != "$CANONICAL_PATH/.env.example" ]; then
    sudo cp "$ENV_SOURCE" "$CANONICAL_ENV"
    log "Copied env from $ENV_SOURCE"
  else
    # Write a pre-filled .env with OpenRouter config
    write_env_atomic "$CANONICAL_ENV" <<'ENVEOF'
# ============================================================
# EldonOpenClaw — Production .env
# Generated by repair script — review and complete as needed
# ============================================================

# ── LLM (OpenRouter) ────────────────────────────────────────
OPENCLAW_CHAT_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=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
OPENAI_BASE_URL=https://openrouter.ai/api/v1

# ── APP ─────────────────────────────────────────────────────
OPENCLAW_ENV=production
OPENCLAW_LOG_LEVEL=info

# ── CONNECTORS ──────────────────────────────────────────────
OPENCLAW_CONNECTOR_CLI=true
OPENCLAW_CONNECTOR_TELEGRAM=false
OPENCLAW_CONNECTOR_VOICE=false

# ── MEMORY ──────────────────────────────────────────────────
OPENCLAW_MEMORY_ENABLED=false

# ── ACTION GATING ───────────────────────────────────────────
OPENCLAW_ACTION_CONFIRM=true
ENVEOF
    log "Created new env file with OpenRouter config"
  fi

fi

ensure_env_permissions "$CANONICAL_ENV"
ok "Verified $CANONICAL_ENV ownership/mode/readability for openclaw user"

# Also ensure a .env symlink exists in the repo for local tooling
if [ ! -f "$CANONICAL_PATH/.env" ]; then
  sudo ln -sf "$CANONICAL_ENV" "$CANONICAL_PATH/.env"
fi

# ── Determine entrypoint ──
log "Detecting entrypoint..."
ENTRYPOINT=""
if python3 -c "import importlib.util; spec = importlib.util.find_spec('openclaw.main')" 2>/dev/null; then
  ENTRYPOINT="-m openclaw.main"
elif [ -f "$CANONICAL_PATH/main.py" ]; then
  ENTRYPOINT="$CANONICAL_PATH/main.py"
fi

# ── Write systemd unit ──
log "Writing systemd unit file..."

sudo tee "$CANONICAL_UNIT" > /dev/null <<UNITEOF
[Unit]
Description=OpenClaw Agent Runtime
Documentation=https://github.com/Eldonlandsupply/openclaw
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=openclaw
Group=openclaw
WorkingDirectory=$CANONICAL_PATH
EnvironmentFile=$CANONICAL_ENV
ExecStart=$CANONICAL_VENV/bin/python ${ENTRYPOINT:-main.py} $CANONICAL_PATH/config.yaml
Restart=always
RestartSec=5
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=openclaw
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/openclaw $CANONICAL_PATH/.data

[Install]
WantedBy=multi-user.target
UNITEOF

log "Unit file written to $CANONICAL_UNIT"

# ============================================================
# PHASE 7: LEGACY CONFLICT REMOVAL
# ============================================================
step "PHASE 7: LEGACY CONFLICT REMOVAL"

{
echo "── LEGACY CONFLICTS HANDLED ─────────────────────────"

# Disable any other openclaw-named services found
systemctl list-unit-files --type=service 2>/dev/null | grep -i openclaw | grep -v "^openclaw.service" | while read svc _; do
  echo "  Disabling legacy service: $svc"
  sudo systemctl stop "$svc" 2>/dev/null || true
  sudo systemctl disable "$svc" 2>/dev/null || true
  # Backup and remove unit file
  find /etc/systemd/system /lib/systemd/system -name "$svc" 2>/dev/null | while read f; do
    cp "$f" "$BACKUP_ROOT/"
    sudo rm "$f"
    echo "  Retired unit file: $f"
  done
done

# Kill any stray openclaw processes not managed by systemd
ps aux | grep -i "python.*openclaw" | grep -v grep | awk '{print $2}' | while read pid; do
  echo "  Killing stray PID $pid"
  kill -TERM "$pid" 2>/dev/null || true
done

# Check cron for openclaw entries and comment them out
if crontab -l 2>/dev/null | grep -qi openclaw; then
  crontab -l 2>/dev/null > "$BACKUP_ROOT/crontab_original.txt"
  crontab -l 2>/dev/null | sed 's/^.*openclaw.*$/#DISABLED_BY_REPAIR: &/' | crontab -
  echo "  Commented out openclaw cron entries (backed up to $BACKUP_ROOT/crontab_original.txt)"
fi

echo "(done)"
echo
} | tee -a "$LOG" >> "$REPORT"

# ============================================================
# PHASE 8: ENABLE AND START SERVICE
# ============================================================
step "PHASE 8: SERVICE ACTIVATION"

log "Reloading systemd daemon..."
sudo systemctl daemon-reload

log "Enabling openclaw service..."
sudo systemctl enable openclaw 2>&1 | tee -a "$LOG"

log "Starting openclaw service..."
sudo systemctl start openclaw 2>&1 | tee -a "$LOG"
sleep 3

# ============================================================
# PHASE 9: VERIFICATION
# ============================================================
step "PHASE 9: VERIFICATION"

{
echo "── SERVICE STATUS ───────────────────────────────────"
systemctl status openclaw --no-pager -l 2>&1 || echo "FAILED to get status"
echo

echo "── RECENT LOGS ──────────────────────────────────────"
journalctl -u openclaw --no-pager -n 30 2>&1 || echo "no logs"
echo

echo "── PROCESS CHECK ────────────────────────────────────"
ps aux | grep -i openclaw | grep -v grep || echo "(not in process list)"
echo

echo "── RESTART TEST ─────────────────────────────────────"
} | tee -a "$LOG" >> "$REPORT"

log "Running restart test..."
sudo systemctl restart openclaw
sleep 4
{
systemctl is-active openclaw && echo "RESTART: ✓ service active after restart" || echo "RESTART: ✗ service NOT active after restart"
echo

echo "── DUPLICATE PROCESS CHECK ──────────────────────────"
COUNT=$(ps aux | grep -i "python.*openclaw" | grep -v grep | wc -l)
echo "  openclaw python processes: $COUNT"
[ "$COUNT" -le 1 ] && echo "  ✓ No duplicates" || echo "  ✗ WARNING: $COUNT processes — investigate"
echo

echo "── VENV SANITY ──────────────────────────────────────"
"$CANONICAL_VENV/bin/python" -c "import pydantic, yaml, aiohttp, dotenv; print('  ✓ Core imports OK')" 2>&1 || echo "  ✗ Import check failed"
echo

echo "── DOCTOR CHECK ─────────────────────────────────────"
cd "$CANONICAL_PATH"
sudo -u openclaw bash -c "source $CANONICAL_ENV 2>/dev/null; $CANONICAL_VENV/bin/python scripts/doctor.py" 2>&1 || echo "  (doctor.py not found or failed — see above)"
echo
} | tee -a "$LOG" >> "$REPORT"

# ============================================================
# FINAL REPORT
# ============================================================
step "FINAL REPORT"

{
echo "========================================================"
echo " CANONICAL DEPLOYMENT SUMMARY"
echo "========================================================"
echo "  repo:      $CANONICAL_PATH"
echo "  branch:    $(git -C "$CANONICAL_PATH" branch --show-current 2>/dev/null || echo unknown)"
echo "  venv:      $CANONICAL_VENV"
echo "  env file:  $CANONICAL_ENV"
echo "  service:   $CANONICAL_SERVICE"
echo "  unit file: $CANONICAL_UNIT"
echo "  backups:   $BACKUP_ROOT"
echo
echo "========================================================"
echo " MAINTENANCE COMMANDS"
echo "========================================================"
echo "  Status:     sudo systemctl status openclaw"
echo "  Logs:       sudo journalctl -u openclaw -f"
echo "  Restart:    sudo systemctl restart openclaw"
echo "  Stop:       sudo systemctl stop openclaw"
echo "  Pull+reload:"
echo "    cd $CANONICAL_PATH"
echo "    sudo git pull origin main"
echo "    sudo systemctl restart openclaw"
echo
echo "========================================================"
echo " OPEN ITEMS"
echo "========================================================"
echo "  1. Verify OPENAI_API_KEY in $CANONICAL_ENV is valid and not rate-limited"
echo "     (Currently set to OpenRouter key — confirm correct endpoint)"
echo "  2. Set TELEGRAM_BOT_TOKEN if Telegram connector is needed"
echo "  3. Set OPENCLAW_EMBED_MODEL + OPENCLAW_MEMORY_ENABLED=true if memory is needed"
echo "  4. Rotate GitHub PAT if it was exposed in chat history"
echo "  5. Azure AD client secret (2acf5611-...) — confirm still valid in Azure portal"
echo
echo "REPORT COMPLETE: $TIMESTAMP"
} | tee -a "$LOG" >> "$REPORT"

echo
echo "════════════════════════════════════════════════════════"
echo "  OpenClaw Repair Complete"
echo "  Report: $REPORT"
echo "  Log:    $LOG"
echo "════════════════════════════════════════════════════════"
echo
sudo systemctl status openclaw --no-pager | head -20
