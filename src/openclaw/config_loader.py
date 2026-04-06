from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class ConfigLoadError(RuntimeError):
    """Raised when runtime configuration cannot be loaded safely."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        msg = f"Missing required config file: {path}"
        raise ConfigLoadError(msg)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"Malformed YAML in {path}: {exc}"
        raise ConfigLoadError(msg) from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = f"Expected mapping at root of config file: {path}"
        raise ConfigLoadError(msg)
    return raw


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_runtime_config() -> dict[str, Any]:
    root = repo_root()
    load_dotenv(root / ".env", override=False)

    env_name = os.environ.get("OPENCLAW_ENV", "development").strip() or "development"
    config_override = os.environ.get("OPENCLAW_CONFIG_FILE")

    base_path = root / "config" / "base.yaml"
    if config_override:
        env_path = Path(config_override).expanduser()
        if not env_path.is_absolute():
            env_path = root / env_path
    else:
        env_path = root / "config" / f"{env_name}.yaml"

    base_config = _load_yaml(base_path)
    env_config = _load_yaml(env_path)

    return _deep_merge(base_config, env_config)
