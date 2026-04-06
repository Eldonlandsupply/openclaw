from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .config_loader import load_runtime_config


class AppConfig(BaseModel):
    app_name: str
    api_host: str = "127.0.0.1"
    api_port: int = 18789
    default_agent: str = "default"


class SchedulerConfig(BaseModel):
    tick_seconds: int = 30


class RuntimeConfig(BaseModel):
    app: AppConfig
    scheduler: SchedulerConfig


class EnvSecrets(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    openclaw_env: str = Field(default="development", alias="OPENCLAW_ENV")
    openclaw_config_file: str | None = Field(default=None, alias="OPENCLAW_CONFIG_FILE")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    env: str
    runtime: RuntimeConfig
    secrets: EnvSecrets

    @model_validator(mode="after")
    def validate_required_secrets(self) -> Settings:
        if self.env == "production" and not self.secrets.openai_api_key:
            msg = "OPENAI_API_KEY is required when OPENCLAW_ENV=production"
            raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    secrets = EnvSecrets()
    runtime_data = load_runtime_config()
    runtime = RuntimeConfig.model_validate(runtime_data)
    return Settings(env=secrets.openclaw_env, runtime=runtime, secrets=secrets)
