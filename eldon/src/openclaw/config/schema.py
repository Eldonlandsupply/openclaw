from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


PLACEHOLDER_VALUES = {"YOUR_CHAT_MODEL", "YOUR_EMBED_MODEL", "CHANGE_ME", "TODO"}


class AppConfig(BaseModel):
    env: str = Field(default="development")
    log_level: str = Field(default="info")


class LLMConfig(BaseModel):
    # Required: LLM provider (minimax is the sole designated provider)
    provider: str = Field(default="minimax")
    # Optional: resolved model id; may be empty if provider sets its own default
    chat_model: Optional[str] = Field(default=None)
    # Optional: embeddings model, required only when memory.enabled is true
    embedding_model: Optional[str] = Field(default=None)
    # Base URL for the OpenAI-compatible endpoint
    base_url: str = Field(default="https://api.minimax.io/v1")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        vv = v.strip().lower()
        if not vv:
            raise ValueError("llm.provider cannot be empty")
        if vv == "openrouter":
            raise ValueError(
                "llm.provider=openrouter is deprecated and must not be used. "
                "Set LLM_PROVIDER=minimax."
            )
        return vv

    @field_validator("chat_model")
    @classmethod
    def validate_chat_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        vv = v.strip()
        if not vv:
            return None
        if vv.upper() in PLACEHOLDER_VALUES:
            raise ValueError("llm.chat_model is still a placeholder. Set YOUR_CHAT_MODEL.")
        return vv

    @field_validator("embedding_model")
    @classmethod
    def validate_embedding_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        vv = v.strip()
        if not vv:
            return None
        if vv.upper() in PLACEHOLDER_VALUES:
            raise ValueError(
                "llm.embedding_model is still a placeholder. "
                "Set YOUR_EMBED_MODEL or leave it blank."
            )
        return vv


class MemoryConfig(BaseModel):
    enabled: bool = Field(default=False)
    vector_store: str = Field(default="local")
    vector_store_path: str = Field(default=".data/vector_store")

    @field_validator("vector_store")
    @classmethod
    def validate_vector_store(cls, v: str) -> str:
        vv = v.strip()
        if not vv:
            raise ValueError("memory.vector_store cannot be empty")
        return vv

    @field_validator("vector_store_path")
    @classmethod
    def validate_vector_store_path(cls, v: str) -> str:
        vv = v.strip()
        if not vv:
            raise ValueError("memory.vector_store_path cannot be empty")
        return vv


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    @model_validator(mode="after")
    def cross_field_gates(self) -> "Settings":
        # If memory is enabled, embedding_model must be set
        if self.memory.enabled:
            if not self.llm.embedding_model:
                raise ValueError(
                    "Memory is enabled but llm.embedding_model is not set. "
                    "Set YOUR_EMBED_MODEL (example: text-embedding-3-small) or disable memory."
                )
        return self
