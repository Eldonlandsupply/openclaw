#!/usr/bin/env python3
"""
scripts/doctor.py — config sanity check for Openclaw (Linux / Pi)

Usage:
    PYTHONPATH=eldon/src python3 scripts/doctor.py

Expected output:
    OK config loaded
    provider=minimax
    chat_model=... (or none)
    embedding_model=... (or none)
    memory_enabled=False
    vector_store_path=.data/vector_store
"""
from __future__ import annotations

import os
import sys

# Ensure eldon/src is on path when invoked directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "eldon", "src"))

from openclaw.config.loader import load_settings  # noqa: E402


def main() -> None:
    s = load_settings("eldon/config.yaml")
    print("OK config loaded")
    print(f"provider={s.llm.provider}")
    print(f"chat_model={s.llm.chat_model or '(none)'}")
    print(f"embedding_model={s.llm.embedding_model or '(none)'}")
    print(f"memory_enabled={s.memory.enabled}")
    print(f"vector_store={s.memory.vector_store}")
    print(f"vector_store_path={s.memory.vector_store_path}")

    # Hard gate: MINIMAX_API_KEY must exist
    minimax_key = os.getenv("MINIMAX_API_KEY", "").strip()
    if not minimax_key:
        print("FAIL: MINIMAX_API_KEY is not set in environment or .env", file=sys.stderr)
        sys.exit(1)
    else:
        print("MINIMAX_API_KEY=OK (set)")

    # Warn if provider is wrong
    provider = os.getenv("LLM_PROVIDER", "minimax").strip().lower()
    if provider != "minimax":
        print(
            f"WARN: LLM_PROVIDER={provider!r} — only 'minimax' is supported. "
            "OpenRouter is deprecated.",
            file=sys.stderr,
        )

    # Warn if OPENAI_BASE_URL is wrong
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    expected_url = "https://api.minimax.io/v1"
    if base_url and base_url != expected_url:
        print(
            f"WARN: OPENAI_BASE_URL={base_url!r} — expected {expected_url!r}",
            file=sys.stderr,
        )

    print("doctor OK")


if __name__ == "__main__":
    main()
