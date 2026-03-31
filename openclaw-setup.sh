#!/usr/bin/env bash
# openclaw-setup.sh — Linux deterministic setup for Eldonlandsupply/openclaw
# Run this line by line or as a script. Does NOT open any interactive editors.
# After this completes, manually edit .env before running openclaw.

set -euo pipefail

# ── 1. Clone ────────────────────────────────────────────────────────────────
if [ ! -d "openclaw" ]; then
  git clone https://github.com/Eldonlandsupply/openclaw.git
fi
cd openclaw

# ── 2. Venv ─────────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

# ── 3. Install deps ──────────────────────────────────────────────────────────
pip install --upgrade pip --quiet

# Try repo-root requirements first, then eldon/ subdirectory
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt --quiet
elif [ -f "eldon/requirements.txt" ]; then
  pip install -r eldon/requirements.txt --quiet
else
  echo "WARNING: no requirements.txt found — skipping pip install"
fi

python3 --version
pip --version

# ── 4. Create .env (no editor — write required keys directly) ────────────────
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    echo "Copied .env.example → .env"
  else
    touch .env
    echo "Created empty .env"
  fi
fi

# Write the required MiniMax keys if not already present
grep -q "^MINIMAX_API_KEY=" .env 2>/dev/null || echo "MINIMAX_API_KEY=" >> .env
grep -q "^LLM_PROVIDER=" .env 2>/dev/null    || echo "LLM_PROVIDER=minimax" >> .env
grep -q "^OPENAI_BASE_URL=" .env 2>/dev/null  || echo "OPENAI_BASE_URL=https://api.minimax.io/v1" >> .env

echo ""
echo "════════════════════════════════════════════"
echo " NEXT STEP: fill in your MINIMAX_API_KEY"
echo " Run:  nano .env"
echo " Set:  MINIMAX_API_KEY=<your-real-key>"
echo "════════════════════════════════════════════"
echo ""
echo "Then verify with:"
echo "  PYTHONPATH=eldon/src python3 scripts/doctor.py"
echo ""
echo "Then run:"
echo "  PYTHONPATH=eldon/src python3 -m openclaw"
