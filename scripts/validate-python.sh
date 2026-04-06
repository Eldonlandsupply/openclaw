#!/usr/bin/env bash
set -euo pipefail

uv sync --dev
PYTHONPATH=src uv run python scripts/preflight.py
PYTHONPATH=src uv run pytest tests -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
