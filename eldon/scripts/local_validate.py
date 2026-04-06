#!/usr/bin/env python3
"""Run local Python validation commands in a deterministic order."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


COMMANDS: tuple[tuple[str, ...], ...] = (
    ("uv", "run", "python", "scripts/preflight.py"),
    ("uv", "run", "pytest", "tests", "-q"),
    ("uv", "run", "ruff", "check", "."),
    ("uv", "run", "ruff", "format", "--check", "."),
    ("uv", "run", "mypy", "src"),
)


def run_command(command: tuple[str, ...]) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env.pop("OPENAI_BASE_URL", None)
    printable = "PYTHONPATH=src " + " ".join(command)
    print(f"\n==> {printable}")
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)


def main() -> int:
    for command in COMMANDS:
        run_command(command)

    print("\nlocal_validate: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
