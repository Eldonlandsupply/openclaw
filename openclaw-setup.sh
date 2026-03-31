#!/usr/bin/env bash
# openclaw-setup.sh — Linux deterministic setup for Eldonlandsupply/openclaw
set -euo pipefail

# ── 1. Clone ────────────────────────────────────────────────────────────────
git clone https://github.com/Eldonlandsupply/openclaw.git
cd openclaw

# ── 2. Venv + install ───────────────────────────────────────────────────────
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

python3 --version
pip --version

# ── 3. .env from template ───────────────────────────────────────────────────
cp .env.example .env
# Edit with your preferred editor — nano, vim, or code
nano .env
# Required fields:
#   MINIMAX_API_KEY=<your-minimax-key>       # LLM provider (not OpenAI)
#   LLM_PROVIDER=minimax
#   OPENAI_BASE_URL=https://api.minimax.io/v1

# ── 4. Config sanity check ──────────────────────────────────────────────────
PYTHONPATH=eldon/src python3 scripts/doctor.py

# ── 5. Run ──────────────────────────────────────────────────────────────────
PYTHONPATH=eldon/src python3 -m openclaw