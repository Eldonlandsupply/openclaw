#!/usr/bin/env python3
"""Refresh bootstrap metadata for directly accessible repositories.

This script is intentionally conservative. It only reads local repository state and
updates timestamps and observed workflow inventory. Remote CI, PR, and security data
must come from direct integrations and should not be fabricated here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CTO_ROOT = ROOT / "agents" / "cto"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def workflow_names() -> list[str]:
    return sorted(path.stem for path in WORKFLOWS_DIR.glob("*.yml"))


def update_json(path: Path, mutate) -> None:
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data, indent=2) + "\n")


def main() -> None:
    timestamp = utc_now()

    update_json(
        CTO_ROOT / "state" / "bootstrap_state.json",
        lambda data: data.update(
            {
                "bootstrapped_at": timestamp,
                "accessible_repositories": [str(ROOT)],
            }
        ),
    )

    update_json(
        CTO_ROOT / "repos" / "health" / "openclaw.json",
        lambda data: data.update({"last_scan": timestamp}),
    )

    update_json(
        CTO_ROOT / "repos" / "pr_tracking" / "openclaw.json",
        lambda data: data.update({"last_scan": timestamp}),
    )

    update_json(
        CTO_ROOT / "repos" / "ci_tracking" / "openclaw.json",
        lambda data: data.update({"last_scan": timestamp, "workflows": workflow_names()}),
    )


if __name__ == "__main__":
    main()
