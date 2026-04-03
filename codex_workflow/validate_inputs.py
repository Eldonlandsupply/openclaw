#!/usr/bin/env python3
import argparse
import json
import pathlib
import re
import sys
from typing import Any

ALLOWED_LOG = {"DEBUG", "INFO", "WARN", "ERROR"}
ALLOWED_BASIS = {"HHV", "LHV"}


class ValidationError(Exception):
    pass


def parse_simple_yaml(path: pathlib.Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []
    current_step: dict[str, Any] | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- id:"):
            if current_step:
                steps.append(current_step)
            current_step = {"id": stripped.split(":", 1)[1].strip()}
            continue

        if current_step is not None and line.startswith("    "):
            key, _, val = stripped.partition(":")
            current_step[key] = coerce(val.strip())
            continue

        key, sep, val = stripped.partition(":")
        if not sep:
            raise ValidationError(f"Malformed line in config: {line}")
        if key == "steps":
            continue
        data[key] = coerce(val.strip())

    if current_step:
        steps.append(current_step)
    data["steps"] = steps
    return data


def coerce(value: str) -> Any:
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def validate(data: dict[str, Any], schema_path: pathlib.Path | None) -> None:
    required = [
        "workflow_name",
        "run_id",
        "repo_root",
        "output_dir",
        "log_level",
        "dry_run",
        "require_clean_git",
        "allow_network",
        "timeout_seconds",
        "energy_basis",
        "steps",
    ]
    for field in required:
        if field not in data:
            raise ValidationError(f"Missing required field: {field}")

    if not re.fullmatch(r"[a-z0-9_-]{3,64}", str(data["workflow_name"])):
        raise ValidationError("workflow_name must match ^[a-z0-9_-]{3,64}$")
    if not re.fullmatch(r"run-[0-9]{8}-[0-9]{4}", str(data["run_id"])):
        raise ValidationError("run_id must match ^run-[0-9]{8}-[0-9]{4}$")

    repo_root = pathlib.Path(str(data["repo_root"]))
    if not repo_root.exists():
        raise ValidationError(f"repo_root does not exist: {repo_root}")

    if data["log_level"] not in ALLOWED_LOG:
        raise ValidationError(f"log_level invalid: {data['log_level']}")
    if data["energy_basis"] not in ALLOWED_BASIS:
        raise ValidationError(f"energy_basis invalid: {data['energy_basis']}")

    timeout = data["timeout_seconds"]
    if not isinstance(timeout, int) or timeout < 30 or timeout > 7200:
        raise ValidationError("timeout_seconds must be integer in [30, 7200]")

    for flag in ["dry_run", "require_clean_git", "allow_network"]:
        if not isinstance(data[flag], bool):
            raise ValidationError(f"{flag} must be boolean")

    if not isinstance(data["steps"], list) or len(data["steps"]) == 0:
        raise ValidationError("steps must be non-empty list")

    for idx, step in enumerate(data["steps"]):
        for step_key in ["id", "enabled", "command"]:
            if step_key not in step:
                raise ValidationError(f"steps[{idx}] missing {step_key}")
        if not re.fullmatch(r"[a-z0-9_-]{2,40}", str(step["id"])):
            raise ValidationError(f"steps[{idx}].id invalid")
        if not isinstance(step["enabled"], bool):
            raise ValidationError(f"steps[{idx}].enabled must be bool")
        if not str(step["command"]).strip():
            raise ValidationError(f"steps[{idx}].command must be non-empty")

    if schema_path:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if schema.get("type") != "object":
            raise ValidationError("Schema sanity check failed: root type must be object")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--schema", required=False)
    args = parser.parse_args()

    config_path = pathlib.Path(args.config)
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}", file=sys.stderr)
        return 2

    schema_path = pathlib.Path(args.schema) if args.schema else None
    if schema_path and not schema_path.exists():
        print(f"[ERROR] Schema file not found: {schema_path}", file=sys.stderr)
        return 3

    try:
        data = parse_simple_yaml(config_path)
        validate(data, schema_path)
    except ValidationError as exc:
        print(f"[ERROR] VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 4

    print("[OK] validation complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
