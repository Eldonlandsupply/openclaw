#!/usr/bin/env python3
import argparse
import json
import pathlib
import re
import sys
from typing import Any


class ValidationError(Exception):
    pass


def strip_inline_comment(raw: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    result: list[str] = []

    for ch in raw:
        if escaped:
            result.append(ch)
            escaped = False
            continue

        if ch == "\\":
            escaped = True
            result.append(ch)
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            result.append(ch)
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            result.append(ch)
            continue

        if ch == "#" and not in_single and not in_double:
            break

        result.append(ch)

    return "".join(result).rstrip()


def parse_scalar(raw: str) -> Any:
    value = strip_inline_comment(raw.strip())
    if value in {"true", "false"}:
        return value == "true"
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    return value


def parse_yaml(path: pathlib.Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1

        if not strip_inline_comment(raw).strip() or raw.lstrip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2 != 0:
            raise ValidationError(f"Invalid indentation at line {i}: '{raw}'")
        stripped = strip_inline_comment(raw).strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ValidationError(f"Parser stack underflow at line {i}")

        parent = stack[-1][1]

        if stripped.startswith("- "):
            if not isinstance(parent, list):
                raise ValidationError(f"List item without list context at line {i}")
            item_body = stripped[2:].strip()
            if ":" in item_body:
                key, value = item_body.split(":", 1)
                node: dict[str, Any] = {key.strip(): parse_scalar(value)}
                parent.append(node)
                stack.append((indent, node))
            else:
                parent.append(parse_scalar(item_body))
            continue

        if ":" not in stripped:
            raise ValidationError(f"Malformed mapping line {i}: '{raw}'")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if not isinstance(parent, dict):
            raise ValidationError(f"Mapping without dict context at line {i}")

        if value:
            parent[key] = parse_scalar(value)
            continue

        next_node: Any = {}
        for j in range(i, len(lines)):
            nxt = lines[j]
            nxt_clean = strip_inline_comment(nxt).strip()
            if not nxt_clean or nxt.lstrip().startswith("#"):
                continue
            next_indent = len(nxt) - len(nxt.lstrip(" "))
            if next_indent <= indent:
                break
            next_node = [] if nxt_clean.startswith("- ") else {}
            break

        parent[key] = next_node
        stack.append((indent, next_node))

    return root


def assert_condition(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def reject_unknown_keys(container: dict[str, Any], allowed: set[str], context: str, errors: list[str]) -> None:
    for key in container.keys():
        if key not in allowed:
            errors.append(f"{context} contains unknown key: {key}")


def validate_contract(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    required_top = [
        "schema_version",
        "workflow",
        "paths",
        "runtime",
        "dependencies",
        "execution",
        "verification",
        "error_policy",
        "energy",
    ]
    allowed_top = set(required_top)

    reject_unknown_keys(data, allowed_top, "root", errors)
    for key in required_top:
        assert_condition(key in data, f"missing required top-level key: {key}", errors)

    if errors:
        return errors

    sections = [
        "workflow",
        "paths",
        "runtime",
        "dependencies",
        "execution",
        "verification",
        "error_policy",
        "energy",
    ]
    for section in sections:
        assert_condition(isinstance(data.get(section), dict), f"{section} must be a map/object", errors)
    if errors:
        return errors

    workflow = data["workflow"]
    paths = data["paths"]
    runtime = data["runtime"]
    deps = data["dependencies"]
    execution = data["execution"]
    verification = data["verification"]
    error_policy = data["error_policy"]
    energy = data["energy"]

    for label, section in [
        ("workflow", workflow),
        ("paths", paths),
        ("runtime", runtime),
        ("dependencies", deps),
        ("execution", execution),
        ("verification", verification),
        ("error_policy", error_policy),
        ("energy", energy),
    ]:
        assert_condition(isinstance(section, dict), f"{label} must be a map", errors)

    if errors:
        return errors

    reject_unknown_keys(workflow, {"name", "run_id", "mode"}, "workflow", errors)
    reject_unknown_keys(paths, {"repo_root", "workspace_root", "output_root", "logs_dir", "allow_write_paths"}, "paths", errors)
    reject_unknown_keys(runtime, {"log_level", "timeout_seconds", "require_clean_git", "allow_network", "dry_run"}, "runtime", errors)
    reject_unknown_keys(deps, {"required_binaries"}, "dependencies", errors)
    reject_unknown_keys(execution, {"steps"}, "execution", errors)
    reject_unknown_keys(verification, {"commands"}, "verification", errors)
    reject_unknown_keys(error_policy, {"fail_fast", "allow_silent_fallbacks"}, "error_policy", errors)
    reject_unknown_keys(energy, {"basis", "mixed_basis_input"}, "energy", errors)

    assert_condition(data["schema_version"] == "1.0.0", "schema_version must be 1.0.0", errors)
    assert_condition(re.fullmatch(r"[a-z0-9_-]{3,64}", str(workflow.get("name", ""))) is not None, "workflow.name invalid", errors)
    assert_condition(re.fullmatch(r"run-[0-9]{8}-[0-9]{4}", str(workflow.get("run_id", ""))) is not None, "workflow.run_id invalid", errors)
    assert_condition(workflow.get("mode") in {"full", "validate_only"}, "workflow.mode must be full or validate_only", errors)

    repo_root = pathlib.Path(str(paths.get("repo_root", "")))
    workspace_root = pathlib.Path(str(paths.get("workspace_root", "")))
    output_root = paths.get("output_root")
    logs_dir = paths.get("logs_dir")
    allow_write_paths = paths.get("allow_write_paths")
    assert_condition(repo_root.exists(), f"paths.repo_root does not exist: {repo_root}", errors)
    assert_condition(workspace_root.exists(), f"paths.workspace_root does not exist: {workspace_root}", errors)
    assert_condition(isinstance(output_root, str) and output_root.strip() != "", "paths.output_root must be non-empty string", errors)
    assert_condition(isinstance(logs_dir, str) and logs_dir.strip() != "", "paths.logs_dir must be non-empty string", errors)
    if allow_write_paths is not None:
        assert_condition(isinstance(allow_write_paths, list) and all(isinstance(p, str) and p.strip() != "" for p in allow_write_paths), "paths.allow_write_paths must be a list of non-empty strings", errors)

    assert_condition(runtime.get("log_level") in {"DEBUG", "INFO", "WARN", "ERROR"}, "runtime.log_level invalid", errors)
    timeout = runtime.get("timeout_seconds")
    assert_condition(isinstance(timeout, int) and 30 <= timeout <= 7200, "runtime.timeout_seconds must be integer in [30, 7200]", errors)
    for flag in ["require_clean_git", "allow_network", "dry_run"]:
        assert_condition(isinstance(runtime.get(flag), bool), f"runtime.{flag} must be boolean", errors)

    required_bins = deps.get("required_binaries")
    assert_condition(isinstance(required_bins, list) and len(required_bins) >= 2, "dependencies.required_binaries must contain at least 2 entries", errors)
    if isinstance(required_bins, list):
        assert_condition("timeout" in required_bins, "dependencies.required_binaries must include timeout", errors)
    if isinstance(required_bins, list):
        for idx, item in enumerate(required_bins):
            assert_condition(re.fullmatch(r"[a-zA-Z0-9._+-]{1,64}", str(item)) is not None, f"dependencies.required_binaries[{idx}] invalid", errors)

    steps = execution.get("steps")
    assert_condition(isinstance(steps, list) and len(steps) > 0, "execution.steps must be a non-empty list", errors)
    if isinstance(steps, list):
        seen_ids: set[str] = set()
        for idx, step in enumerate(steps):
            assert_condition(isinstance(step, dict), f"execution.steps[{idx}] must be a map", errors)
            if not isinstance(step, dict):
                continue
            reject_unknown_keys(step, {"id", "enabled", "command", "retry_count", "timeout_seconds"}, f"execution.steps[{idx}]", errors)
            sid = str(step.get("id", ""))
            assert_condition(re.fullmatch(r"[a-z0-9_-]{2,40}", sid) is not None, f"execution.steps[{idx}].id invalid", errors)
            assert_condition(sid not in seen_ids, f"execution.steps[{idx}].id is duplicated: {sid}", errors)
            seen_ids.add(sid)
            assert_condition(isinstance(step.get("enabled"), bool), f"execution.steps[{idx}].enabled must be boolean", errors)
            assert_condition(isinstance(step.get("command"), str) and step["command"].strip() != "", f"execution.steps[{idx}].command must be non-empty string", errors)
            retry = step.get("retry_count")
            assert_condition(isinstance(retry, int) and 0 <= retry <= 3, f"execution.steps[{idx}].retry_count must be integer in [0,3]", errors)
            st = step.get("timeout_seconds")
            assert_condition(isinstance(st, int) and 5 <= st <= 7200, f"execution.steps[{idx}].timeout_seconds must be integer in [5,7200]", errors)

    commands = verification.get("commands")
    assert_condition(isinstance(commands, list) and len(commands) > 0, "verification.commands must be non-empty list", errors)
    if isinstance(commands, list):
        for idx, cmd in enumerate(commands):
            assert_condition(isinstance(cmd, str) and cmd.strip() != "", f"verification.commands[{idx}] must be non-empty string", errors)

    assert_condition(error_policy.get("fail_fast") is True, "error_policy.fail_fast must be true", errors)
    assert_condition(error_policy.get("allow_silent_fallbacks") is False, "error_policy.allow_silent_fallbacks must be false", errors)

    assert_condition(energy.get("basis") in {"HHV", "LHV"}, "energy.basis must be HHV or LHV", errors)
    assert_condition(isinstance(energy.get("mixed_basis_input"), bool), "energy.mixed_basis_input must be boolean", errors)
    if energy.get("mixed_basis_input"):
        errors.append("energy.mixed_basis_input=true is not allowed, normalize to a single basis before execution")

    return errors


def build_runtime_contract(data: dict[str, Any], config_path: pathlib.Path) -> dict[str, Any]:
    return {
        "schema_version": data["schema_version"],
        "config_path": str(config_path.resolve()),
        "workflow": data["workflow"],
        "paths": data["paths"],
        "runtime": data["runtime"],
        "dependencies": data["dependencies"],
        "execution": data["execution"],
        "verification": data["verification"],
        "error_policy": data["error_policy"],
        "energy": data["energy"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--schema", required=False)
    parser.add_argument("--emit-runtime", required=False)
    args = parser.parse_args()

    config_path = pathlib.Path(args.config)
    if not config_path.exists():
        print(f"[ERROR] VALIDATION_FAILED: config file not found: {config_path}", file=sys.stderr)
        return 2

    if args.schema:
        schema_path = pathlib.Path(args.schema)
        if not schema_path.exists():
            print(f"[ERROR] VALIDATION_FAILED: schema file not found: {schema_path}", file=sys.stderr)
            return 3
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[ERROR] VALIDATION_FAILED: schema JSON parse failed: {exc}", file=sys.stderr)
            return 4

        if schema.get("type") != "object":
            print("[ERROR] VALIDATION_FAILED: schema sanity check failed: root type must be object", file=sys.stderr)
            return 4

    try:
        data = parse_yaml(config_path)
        errors = validate_contract(data)
    except ValidationError as exc:
        print(f"[ERROR] VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 5
    except Exception as exc:
        print(f"[ERROR] VALIDATION_FAILED: unexpected exception: {exc}", file=sys.stderr)
        return 7

    if errors:
        print("[ERROR] VALIDATION_FAILED", file=sys.stderr)
        for index, err in enumerate(errors, start=1):
            print(f"  {index}. {err}", file=sys.stderr)
        return 6

    runtime_contract = build_runtime_contract(data, config_path)
    if args.emit_runtime:
        emit_path = pathlib.Path(args.emit_runtime)
        emit_path.parent.mkdir(parents=True, exist_ok=True)
        emit_path.write_text(json.dumps(runtime_contract, indent=2) + "\n", encoding="utf-8")

    print("[OK] validation complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
