"""
scripts/run_optimizer.py — CLI entry point for the nightly optimizer.

Usage (from eldon/ repo root with PYTHONPATH=src):
    python scripts/run_optimizer.py
    python scripts/run_optimizer.py --hours 48
    python scripts/run_optimizer.py --dry-run

Designed to be called from a systemd timer nightly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

_repo_src = Path(__file__).resolve().parent.parent / "src"
if str(_repo_src) not in sys.path:
    sys.path.insert(0, str(_repo_src))

_repo_root = Path(__file__).resolve().parent.parent


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def _run(hours: int, dry_run: bool, no_llm: bool) -> int:
    from openclaw.learning.optimizer import NightlyOptimizer
    from openclaw.learning.crystallizer import PatternCrystallizer
    from openclaw.learning.adas import ADASArchive

    data_dir = _repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    audit_log = _repo_root / "action_allowlist" / "audit_log.jsonl"
    candidates_path = _repo_root / "action_allowlist" / "action_candidates.json"
    observations_path = data_dir / "_crystallizer_observations.json"
    adas_path = data_dir / "adas_archive.json"

    crystallizer = PatternCrystallizer(
        candidates_path=candidates_path,
        observations_path=observations_path,
    )
    adas = ADASArchive(path=adas_path)

    llm = None
    if not no_llm:
        try:
            from openclaw.config import get_config
            from openclaw.chat.client import ChatClient
            cfg = get_config()
            if cfg.llm.provider != "none":
                llm = ChatClient(cfg)
                logging.getLogger(__name__).info("LLM client: %s/%s", cfg.llm.provider, cfg.llm.chat_model)
        except Exception as e:
            logging.getLogger(__name__).warning("LLM unavailable, skipping ADAS generation: %s", e)

    optimizer = NightlyOptimizer(
        audit_log_path=audit_log,
        crystallizer=crystallizer,
        adas_archive=adas,
        llm=llm,
        max_hours=hours,
    )

    if dry_run:
        print("[dry-run] Would run optimizer with:")
        print(f"  audit_log:  {audit_log}")
        print(f"  hours:      {hours}")
        print(f"  llm:        {'yes' if llm else 'no'}")
        return 0

    report = await optimizer.run()
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClaw nightly optimizer")
    parser.add_argument("--hours", type=int, default=24, help="Audit log window in hours (default: 24)")
    parser.add_argument("--dry-run", action="store_true", help="Print config and exit without running")
    parser.add_argument("--no-llm", action="store_true", help="Skip ADAS candidate generation")
    parser.add_argument("--log-level", default="INFO", help="Log level (default: INFO)")
    args = parser.parse_args()

    _setup_logging(args.log_level)
    sys.exit(asyncio.run(_run(args.hours, args.dry_run, args.no_llm)))


if __name__ == "__main__":
    main()
