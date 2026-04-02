#!/usr/bin/env bash
# =============================================================================
# verify_lola_telegram.sh
# 
# Deterministic end-to-end verification of Lola's Telegram messaging path.
# Run this on the Pi to confirm:
#   1. Service config is sane (correct env file, correct ExecStart)
#   2. MINIMAX_API_KEY is set in the live env
#   3. TELEGRAM_BOT_TOKEN is set in the live env
#   4. OPENCLAW_CONNECTOR_TELEGRAM (or CONNECTOR_TELEGRAM) is true
#   5. pytest suite passes (all 10 test classes, no network calls)
#   6. Live Telegram getMe API call succeeds with real bot token
#   7. Service is running and healthy
#
# Usage:
#   chmod +x verify_lola_telegram.sh
#   sudo bash verify_lola_telegram.sh
#
# Expected: all checks print OK. Any FAIL exits non-zero.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0

ok()   { echo -e "${GREEN}[OK]${NC}   $1"; ((PASS++)); }
fail() { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL++)); }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

OPENCLAW_DIR="/opt/openclaw"
ELDON_DIR="$OPENCLAW_DIR/eldon"
VENV="$OPENCLAW_DIR/.venv"
ENV_FILE="/etc/openclaw/openclaw.env"
SERVICE="openclaw"

echo ""
echo "============================================================"
echo "  Lola / OpenClaw — Telegram Routing Verification"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# 1. Directory and venv
# ---------------------------------------------------------------------------

info "Checking filesystem..."

[ -d "$OPENCLAW_DIR" ] && ok "Repo root exists: $OPENCLAW_DIR" || fail "Missing: $OPENCLAW_DIR"
[ -d "$ELDON_DIR" ] && ok "Eldon dir exists: $ELDON_DIR" || fail "Missing: $ELDON_DIR"
[ -f "$VENV/bin/python3" ] && ok "Venv exists: $VENV" || fail "Missing venv: $VENV"
[ -f "$ENV_FILE" ] && ok "Env file exists: $ENV_FILE" || fail "Missing env file: $ENV_FILE"

# ---------------------------------------------------------------------------
# 2. Service config sanity
# ---------------------------------------------------------------------------

info "Checking systemd service..."

if systemctl is-enabled "$SERVICE" &>/dev/null; then
    ok "Service is enabled: $SERVICE"
else
    fail "Service not enabled: $SERVICE"
fi

EXEC_START=$(systemctl cat "$SERVICE" 2>/dev/null | grep "^ExecStart" | head -1)
if echo "$EXEC_START" | grep -q "eldon/config.yaml"; then
    ok "ExecStart references correct config.yaml"
else
    fail "ExecStart does not reference eldon/config.yaml — check: $EXEC_START"
fi

ENV_FILE_LINE=$(systemctl cat "$SERVICE" 2>/dev/null | grep "EnvironmentFile" | head -1)
if echo "$ENV_FILE_LINE" | grep -q "/etc/openclaw"; then
    ok "EnvironmentFile points to /etc/openclaw: $ENV_FILE_LINE"
else
    fail "EnvironmentFile not pointing to /etc/openclaw — found: $ENV_FILE_LINE"
fi

# ---------------------------------------------------------------------------
# 3. Critical env vars in live env file
# ---------------------------------------------------------------------------

info "Checking env file contents..."

check_env_var() {
    local var="$1"
    local val
    val=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '[:space:]')
    if [ -n "$val" ] && [ "$val" != "YOUR_${var}" ] && [ "${val:0:4}" != "TODO" ]; then
        ok "$var is set (${#val} chars)"
        echo "$val"
    else
        fail "$var is missing or still a placeholder in $ENV_FILE"
        echo ""
    fi
}

MINIMAX_KEY=$(check_env_var "MINIMAX_API_KEY")
TG_TOKEN=$(check_env_var "TELEGRAM_BOT_TOKEN")
TG_CHAT=$(check_env_var "TELEGRAM_ALLOWED_CHAT_IDS")

# Check LLM_PROVIDER
LLM_PROVIDER=$(grep "^LLM_PROVIDER=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' || echo "")
if [ "$LLM_PROVIDER" = "minimax" ]; then
    ok "LLM_PROVIDER=minimax (correct)"
elif [ -z "$LLM_PROVIDER" ]; then
    # Check config.yaml default
    YAML_DEFAULT=$(grep "provider:" "$ELDON_DIR/config.yaml" 2>/dev/null | head -1 | sed 's/.*minimax.*/minimax/' || echo "")
    if [ "$YAML_DEFAULT" = "minimax" ]; then
        ok "LLM_PROVIDER not in env; config.yaml defaults to minimax"
    else
        fail "LLM_PROVIDER not set and config.yaml default is not minimax"
    fi
else
    fail "LLM_PROVIDER=$LLM_PROVIDER (expected minimax)"
fi

# OpenRouter key must NOT be set (or must be empty/dead)
OR_KEY=$(grep "^OPENROUTER_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' || echo "")
if [ -n "$OR_KEY" ] && [ "$OR_KEY" != "YOUR_OPENROUTER_KEY" ]; then
    fail "OPENROUTER_API_KEY is SET — this may cause contradictory env. Remove it from $ENV_FILE"
else
    ok "OPENROUTER_API_KEY is absent/empty (correct)"
fi

# Telegram connector enabled
TG_ENABLED=""
for var in OPENCLAW_CONNECTOR_TELEGRAM CONNECTOR_TELEGRAM; do
    val=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '[:space:]' || echo "")
    if [ "$val" = "true" ] || [ "$val" = "1" ] || [ "$val" = "yes" ]; then
        ok "$var=true (Telegram connector enabled)"
        TG_ENABLED="true"
        break
    fi
done
[ -z "$TG_ENABLED" ] && fail "Neither OPENCLAW_CONNECTOR_TELEGRAM nor CONNECTOR_TELEGRAM is set to true in $ENV_FILE"

# ---------------------------------------------------------------------------
# 4. pytest — offline unit + integration tests
# ---------------------------------------------------------------------------

info "Running pytest suite (no network)..."

cd "$ELDON_DIR"
PYTHONPATH="$ELDON_DIR/src" "$VENV/bin/pytest" \
    tests/test_provider_routing.py \
    tests/test_telegram_connector.py \
    tests/test_telegram_e2e.py \
    -v --tb=short --no-header 2>&1 | tee /tmp/openclaw_pytest.log

if [ $? -eq 0 ]; then
    ok "All pytest tests passed"
else
    fail "pytest failures — see /tmp/openclaw_pytest.log"
fi

# ---------------------------------------------------------------------------
# 5. Live Telegram getMe API call
# ---------------------------------------------------------------------------

info "Testing live Telegram bot token..."

if [ -n "$TG_TOKEN" ]; then
    GETME=$(curl -s --max-time 10 \
        "https://api.telegram.org/bot${TG_TOKEN}/getMe" 2>/dev/null || echo "{}")

    if echo "$GETME" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
        BOT_USERNAME=$(echo "$GETME" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['username'])" 2>/dev/null || echo "unknown")
        ok "Telegram getMe: bot is valid (@$BOT_USERNAME)"
    else
        ERROR=$(echo "$GETME" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description','unknown'))" 2>/dev/null || echo "parse failed")
        fail "Telegram getMe failed: $ERROR"
    fi
else
    fail "TELEGRAM_BOT_TOKEN is empty — cannot test live API"
fi

# ---------------------------------------------------------------------------
# 6. MiniMax API health check
# ---------------------------------------------------------------------------

info "Testing live MiniMax API key..."

if [ -n "$MINIMAX_KEY" ]; then
    MINIMAX_RESP=$(curl -s --max-time 10 \
        -H "Authorization: Bearer $MINIMAX_KEY" \
        -H "Content-Type: application/json" \
        -d '{"model":"MiniMax-M1-mini","max_tokens":5,"messages":[{"role":"user","content":"hi"}]}' \
        "https://api.minimax.io/v1/chat/completions" 2>/dev/null || echo "{}")

    STATUS=$(echo "$MINIMAX_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('choices'):
    print('ok')
elif 'error' in d:
    print('error:' + str(d['error']))
else:
    print('unknown:' + str(d)[:100])
" 2>/dev/null || echo "parse_failed")

    if [ "$STATUS" = "ok" ]; then
        ok "MiniMax API key is valid and returning completions"
    else
        fail "MiniMax API call failed: $STATUS"
    fi
else
    fail "MINIMAX_API_KEY is empty — cannot test live API"
fi

# ---------------------------------------------------------------------------
# 7. Service running status
# ---------------------------------------------------------------------------

info "Checking service runtime..."

if systemctl is-active "$SERVICE" &>/dev/null; then
    ok "Service is active: $SERVICE"
    # Check recent logs for Telegram connector startup
    if journalctl -u "$SERVICE" -n 50 --no-pager 2>/dev/null | grep -q "Telegram connector active"; then
        ok "Logs show Telegram connector started successfully"
    else
        fail "No 'Telegram connector active' in recent logs — check: journalctl -u $SERVICE -n 100"
    fi
    # Check for 401 errors in recent logs
    if journalctl -u "$SERVICE" -n 50 --no-pager 2>/dev/null | grep -qi "401\|user not found\|unauthorized"; then
        fail "401/Unauthorized errors found in recent logs — provider misconfiguration likely"
    else
        ok "No 401 errors in recent logs"
    fi
else
    fail "Service not running: $SERVICE — start with: sudo systemctl start $SERVICE"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "============================================================"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}"
echo "============================================================"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}VERIFICATION FAILED — fix the items above before deploying.${NC}"
    exit 1
else
    echo -e "${GREEN}ALL CHECKS PASSED — Lola Telegram routing is operational.${NC}"
    exit 0
fi
