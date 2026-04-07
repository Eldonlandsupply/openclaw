#!/usr/bin/env python3
"""Fast local sanity checks for the Python package layout."""

from __future__ import annotations

import importlib
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"


REQUIRED_IMPORTS = (
    "openclaw",
    "openclaw.config",
    "openclaw.main",
)


def _assert_paths() -> None:
    if not SRC_DIR.exists():
        raise RuntimeError(f"Expected src directory at {SRC_DIR}")
    if os.environ.get("PYTHONPATH") is None:
        raise RuntimeError("PYTHONPATH must include src for local validation")


def _assert_imports() -> None:
    failures: list[str] = []
    for module_name in REQUIRED_IMPORTS:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{module_name}: {exc}")

    if failures:
        raise RuntimeError("Import failures in preflight:\n" + "\n".join(failures))


def main() -> int:
    _assert_paths()
    _assert_imports()
    print("preflight: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
