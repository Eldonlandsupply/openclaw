from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from openclaw.settings import get_settings  # noqa: E402


def main() -> int:
    try:
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 1

    print(f"environment={settings.env}")
    print(f"app_name={settings.runtime.app.app_name}")
    print(f"api_bind={settings.runtime.app.api_host}:{settings.runtime.app.api_port}")
    print(f"scheduler_tick={settings.runtime.scheduler.tick_seconds}")
    print(f"default_agent={settings.runtime.app.default_agent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
