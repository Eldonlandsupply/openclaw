"""
Centralized config: secrets from .env / environment, non-secrets from config.yaml.
Fails loudly if misconfigured. Prints a redacted summary on boot.

config.yaml supports ${VAR} and ${VAR:default} substitution from environment.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Environment variable expansion ────────────────────────────────────────

_ENV_TOKEN = re.compile(r"^\$\{([^}]+)\}$")
_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})


def _parse_env_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    return default


def _expand(value: Any) -> Any:
    """Recursively expand ${VAR} and ${VAR:default} tokens in YAML values."""
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, str):
        m = _ENV_TOKEN.match(value.strip())
        if m:
            inner = m.group(1)
            if ":" in inner:
                var, default = inner.split(":", 1)
                return os.environ.get(var.strip(), default)
            return os.environ.get(inner.strip(), "")
    return value


# ── Config section classes ─────────────────────────────────────────────────

class LLMConfig:
    def __init__(self, **data: Any) -> None:
        self.provider = str(data.get("provider", "none"))
        self.chat_model = str(data.get("chat_model", "grok-3-mini"))
        raw_embed = data.get("embedding_model")
        self.embedding_model = str(raw_embed) if raw_embed else None
        raw_base = data.get("base_url")
        self.base_url = str(raw_base).strip() if raw_base else None


class RuntimeConfig:
    def __init__(self, **data: Any) -> None:
        self.tick_seconds = int(data.get("tick_seconds", 10))
        self.log_level = str(data.get("log_level", "INFO")).upper()
        self.data_dir = str(data.get("data_dir", "./data"))
        raw_dry = data.get("dry_run", True)
        if isinstance(raw_dry, str):
            self.dry_run = raw_dry.lower() not in ("false", "0", "no")
        else:
            self.dry_run = bool(raw_dry)


class ConnectorCliConfig:
    def __init__(self, **data: Any) -> None:
        raw = data.get("enabled", True)
        self.enabled = raw if isinstance(raw, bool) else str(raw).lower() not in ("false", "0", "no")


class ConnectorTelegramConfig:
    def __init__(self, **data: Any) -> None:
        raw = data.get("enabled", False)
        self.enabled = raw if isinstance(raw, bool) else str(raw).lower() in ("true", "1", "yes")


class ConnectorWhatsAppConfig:
    def __init__(self, **data: Any) -> None:
        raw = data.get("enabled", False)
        self.enabled = raw if isinstance(raw, bool) else str(raw).lower() in ("true", "1", "yes")
        self.bridge_url = str(data.get("bridge_url", "http://127.0.0.1:8181"))
        self.poll_interval = int(data.get("poll_interval", 5))
        self.bridge_db = str(data.get("bridge_db", "/var/lib/wabridge/wabridge.db"))


class ConnectorsConfig:
    def __init__(self, **data: Any) -> None:
        cli_raw = data.get("cli", {})
        if isinstance(cli_raw, (bool, str)):
            cli_raw = {"enabled": cli_raw}
        self.cli = ConnectorCliConfig(**(cli_raw or {}))

        tg_raw = data.get("telegram", {})
        if isinstance(tg_raw, (bool, str)):
            tg_raw = {"enabled": tg_raw}
        self.telegram = ConnectorTelegramConfig(**(tg_raw or {}))

        wa_raw = data.get("whatsapp", {})
        if isinstance(wa_raw, (bool, str)):
            wa_raw = {"enabled": wa_raw}
        self.whatsapp = ConnectorWhatsAppConfig(**(wa_raw or {}))


class ActionsConfig:
    def __init__(self, **data: Any) -> None:
        self.allowlist = list(data.get("allowlist", ["echo"]))
        raw = data.get("require_confirm", data.get("require_confirmation", False))
        if isinstance(raw, str):
            self.require_confirm = raw.lower() in ("true", "1", "yes")
        else:
            self.require_confirm = bool(raw)


class HealthConfig:
    def __init__(self, **data: Any) -> None:
        self.enabled = bool(data.get("enabled", True))
        self.host = str(data.get("host", "127.0.0.1"))
        self.port = int(data.get("port", 8080))


# ── Secrets from environment / .env ───────────────────────────────────────

def _find_env_file() -> str:
    """Resolve .env relative to the repo root, not the working directory."""
    candidates = [
        Path(".env"),
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path("/etc/openclaw/openclaw.env"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return ".env"  # fallback; pydantic-settings won't error if missing


def _read_env_file_value(env_path: Path, key: str) -> str | None:
    """Read one env key from a dotenv-style file without exposing secrets."""
    if not env_path.exists() or not env_path.is_file():
        return None
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            name, value = raw.split("=", 1)
            if name.strip() != key:
                continue
            val = value.strip()
            if val.startswith(("'", '"')) and val.endswith(("'", '"')) and len(val) >= 2:
                val = val[1:-1]
            return val
    except OSError:
        return None
    return None


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # xAI (Grok)
    xai_api_key: Optional[str] = None
    # OpenAI direct
    openai_api_key: Optional[str] = None
    # OpenRouter
    openrouter_api_key: Optional[str] = None
    # Messaging
    telegram_bot_token: Optional[str] = None
    telegram_allowed_chat_ids: Optional[str] = None
    whatsapp_allowed_numbers: Optional[str] = None
    # Email
    gmail_user: Optional[str] = None
    gmail_app_password: Optional[str] = None
    notification_email: Optional[str] = None
    # Outlook / Microsoft Graph
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_client_secret: Optional[str] = None
    outlook_user: Optional[str] = None
    # CRM
    attio_api_key: Optional[str] = None
    minimax_api_key: Optional[str] = None
    # Storage
    sqlite_path: str = "./data/openclaw.db"

    @property
    def allowed_chat_ids(self) -> list[int]:
        if not self.telegram_allowed_chat_ids:
            return []
        return [int(x.strip()) for x in self.telegram_allowed_chat_ids.split(",") if x.strip()]

    @property
    def whatsapp_allowed_numbers_list(self) -> list[str]:
        if not self.whatsapp_allowed_numbers:
            return []
        return [x.strip() for x in self.whatsapp_allowed_numbers.split(",") if x.strip()]


# ── Valid sets ─────────────────────────────────────────────────────────────

_VALID_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "openrouter", "xai", "none"})
_VALID_LOG_LEVELS: frozenset[str] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


# ── Merged app config ──────────────────────────────────────────────────────

class AppConfig:
    """Single object holding all config. Created once at startup."""

    def __init__(self, yaml_path: str = "config.yaml") -> None:
        self._env_file = Path(_find_env_file())
        self._dotenv_loaded = False
        self._env_file_exists = self._env_file.exists()
        self._env_file_readable = os.access(self._env_file, os.R_OK) if self._env_file_exists else False
        self._telegram_env_value = None
        self._telegram_intent_from_file = False
        self._telegram_env_present = False
        self._yaml_defaults_used: list[dict[str, str]] = []

        if self._env_file_exists:
            self._telegram_env_value = _read_env_file_value(
                self._env_file, "OPENCLAW_CONNECTOR_TELEGRAM"
            )
            self._telegram_intent_from_file = _parse_env_bool(self._telegram_env_value, default=False)

        self._telegram_env_present = os.getenv("OPENCLAW_CONNECTOR_TELEGRAM") is not None
        self.secrets = Secrets()
        self._yaml_path = yaml_path
        self._load_yaml(yaml_path)
        self._validate()

    def _load_yaml(self, path: str) -> None:
        # load_dotenv must run before YAML token expansion. If .env is unreadable,
        # connector flags can silently fall back to config defaults.
        self._dotenv_loaded = bool(load_dotenv(dotenv_path=self._env_file, override=False))

        p = Path(path)
        if not p.exists():
            print(
                f"FATAL: config file not found: {path}\n"
                "       cp config.yaml.example config.yaml  # then edit it",
                file=sys.stderr,
            )
            sys.exit(1)

        with p.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        expanded = _expand(raw)
        self._yaml_defaults_used = []
        connectors = raw.get("connectors") if isinstance(raw, dict) else {}
        if isinstance(connectors, dict):
            telegram_token = connectors.get("telegram")
            if isinstance(telegram_token, str):
                m = _ENV_TOKEN.match(telegram_token.strip())
                if m:
                    inner = m.group(1)
                    if ":" in inner:
                        env_key, default = inner.split(":", 1)
                        env_key = env_key.strip()
                        if os.getenv(env_key) is None:
                            self._yaml_defaults_used.append(
                                {"path": "connectors.telegram", "env_key": env_key, "default": default}
                            )

        self.llm = LLMConfig(**(expanded.get("llm") or {}))
        self.runtime = RuntimeConfig(**(expanded.get("runtime") or {}))
        self.connectors = ConnectorsConfig(**(expanded.get("connectors") or {}))
        self.actions = ActionsConfig(**(expanded.get("actions") or {}))
        self.health = HealthConfig(**(expanded.get("health") or {}))

    def _validate(self) -> None:
        self._telegram_env_present = os.getenv("OPENCLAW_CONNECTOR_TELEGRAM") is not None
        if self.llm.provider not in _VALID_PROVIDERS:
            self._fatal(
                f"llm.provider must be one of {sorted(_VALID_PROVIDERS)}, "
                f"got: {self.llm.provider!r}"
            )
        if self.runtime.log_level not in _VALID_LOG_LEVELS:
            self._fatal(
                f"runtime.log_level must be one of {sorted(_VALID_LOG_LEVELS)}, "
                f"got: {self.runtime.log_level!r}"
            )
        if self.llm.provider == "openai" and not self.secrets.openai_api_key:
            self._fatal("llm.provider=openai but OPENAI_API_KEY is not set")
        if self.llm.provider == "openrouter" and not self.secrets.openrouter_api_key:
            self._fatal("llm.provider=openrouter but OPENROUTER_API_KEY is not set")
        if self.llm.provider == "xai" and not self.secrets.xai_api_key:
            self._fatal("llm.provider=xai but XAI_API_KEY is not set")
        if self.connectors.telegram.enabled and not self.secrets.telegram_bot_token:
            self._fatal("connectors.telegram.enabled=true but TELEGRAM_BOT_TOKEN is not set")
        if self.connectors.whatsapp.enabled and not self.secrets.whatsapp_allowed_numbers:
            self._fatal("connectors.whatsapp.enabled=true but WHATSAPP_ALLOWED_NUMBERS is not set")
        Path(self.runtime.data_dir).mkdir(parents=True, exist_ok=True)

        if self._telegram_intent_from_file and not self._dotenv_loaded and not self._telegram_env_present:
            self._fatal(
                "OPENCLAW_CONNECTOR_TELEGRAM=true is set in env file intent, "
                f"but runtime did not load {self._env_file}. Check env file ownership/permissions."
            )

        for default_use in self._yaml_defaults_used:
            if default_use["path"] == "connectors.telegram":
                print(
                    "CONFIG WARNING: connectors.telegram fell back to default "
                    f"{default_use['default']!r} because env var {default_use['env_key']} was absent.",
                    file=sys.stderr,
                )

    @staticmethod
    def _fatal(msg: str) -> None:
        print(f"FATAL CONFIG ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    def summary(self) -> dict:
        return {
            "llm": {
                "provider": self.llm.provider,
                "chat_model": self.llm.chat_model,
                "embedding_model": self.llm.embedding_model,
            },
            "runtime": {
                "tick_seconds": self.runtime.tick_seconds,
                "log_level": self.runtime.log_level,
                "data_dir": self.runtime.data_dir,
                "dry_run": self.runtime.dry_run,
            },
            "connectors": {
                "cli": self.connectors.cli.enabled,
                "telegram": self.connectors.telegram.enabled,
                "whatsapp": self.connectors.whatsapp.enabled,
            },
            "actions": {
                "allowlist": self.actions.allowlist,
                "require_confirm": self.actions.require_confirm,
            },
            "health": {
                "enabled": self.health.enabled,
                "host": self.health.host,
                "port": self.health.port,
            },
            "secrets": {
                "xai_api_key": "SET" if self.secrets.xai_api_key else "NOT SET",
                "openai_api_key": "SET" if self.secrets.openai_api_key else "NOT SET",
                "openrouter_api_key": "SET" if self.secrets.openrouter_api_key else "NOT SET",
                "telegram_bot_token": "SET" if self.secrets.telegram_bot_token else "NOT SET",
                "whatsapp_allowed_numbers": "SET" if self.secrets.whatsapp_allowed_numbers else "NOT SET",
                "gmail_user": self.secrets.gmail_user or "NOT SET",
                "notification_email": self.secrets.notification_email or "NOT SET",
                "attio_api_key": "SET" if self.secrets.attio_api_key else "NOT SET",
                "minimax_api_key": "SET" if self.secrets.minimax_api_key else "NOT SET",
                "sqlite_path": self.secrets.sqlite_path,
            },
            "config_diagnostics": {
                "env_file": str(self._env_file),
                "env_file_exists": self._env_file_exists,
                "env_file_readable": self._env_file_readable,
                "dotenv_loaded": self._dotenv_loaded,
                "telegram_env_present": self._telegram_env_present,
                "telegram_intent_from_env_file": self._telegram_intent_from_file,
            },
        }

    def connector_state_reasons(self) -> dict[str, str]:
        reasons: dict[str, str] = {}
        reasons["cli"] = "enabled by config" if self.connectors.cli.enabled else "disabled by config"
        if self.connectors.telegram.enabled:
            reasons["telegram"] = "enabled via OPENCLAW_CONNECTOR_TELEGRAM/config"
        else:
            if self._telegram_intent_from_file and not self._telegram_env_present:
                reasons["telegram"] = (
                    "disabled because OPENCLAW_CONNECTOR_TELEGRAM was not loaded from env file"
                )
            else:
                reasons["telegram"] = "disabled by config/default"
        reasons["whatsapp"] = (
            "enabled via OPENCLAW_CONNECTOR_WHATSAPP/config"
            if self.connectors.whatsapp.enabled
            else "disabled by config/default"
        )
        return reasons


# ── Module-level singleton ─────────────────────────────────────────────────

_config: Optional[AppConfig] = None


def get_config(yaml_path: str = "config.yaml") -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig(yaml_path=yaml_path)
    return _config


def reset_config() -> None:
    """For use in tests only."""
    global _config
    _config = None
