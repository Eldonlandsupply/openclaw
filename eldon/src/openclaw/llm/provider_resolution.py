from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class LLMProviderResolutionError(RuntimeError):
    """Raised when LLM provider config is contradictory or incomplete."""


@dataclass(frozen=True)
class ResolvedLlmProvider:
    provider: str
    model: str
    base_url: str
    api_key: str
    api_key_source: str


_PROVIDER_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "minimax": "https://api.minimax.io/v1",
}


def _normalize_provider(provider: str | None) -> str:
    return (provider or "none").strip().lower()


def _looks_like_openrouter_base(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.strip().lower()
    return "openrouter.ai" in lowered


def _pick_api_key(provider: str, env: Mapping[str, str], explicit: str | None) -> tuple[str, str]:
    if explicit and explicit.strip():
        return explicit.strip(), "config"

    key_var_by_provider = {
        "openrouter": "OPENROUTER_API_KEY",
        "openai": "OPENAI_API_KEY",
        "xai": "XAI_API_KEY",
        "minimax": "MINIMAX_API_KEY",
    }
    env_var = key_var_by_provider.get(provider)
    if not env_var:
        return "", "none"
    value = (env.get(env_var) or "").strip()
    return value, (f"env:{env_var}" if value else "none")


def resolve_llm_provider(
    *,
    provider: str,
    model: str,
    configured_base_url: str | None = None,
    configured_api_key: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedLlmProvider:
    resolved_provider = _normalize_provider(provider)
    resolved_model = (model or "").strip()
    env_map = env or os.environ

    if resolved_provider not in {"openrouter", "openai", "xai", "minimax", "none"}:
        raise LLMProviderResolutionError(f"Unsupported provider: {resolved_provider}")

    if resolved_provider == "none":
        return ResolvedLlmProvider(
            provider="none",
            model=resolved_model,
            base_url="",
            api_key="",
            api_key_source="none",
        )

    cleaned_base_url = (configured_base_url or "").strip()
    if resolved_provider == "openai":
        selected_base_url = cleaned_base_url or _PROVIDER_BASE_URLS[resolved_provider]
    else:
        selected_base_url = _PROVIDER_BASE_URLS[resolved_provider]

    if resolved_provider == "minimax" and cleaned_base_url:
        if _looks_like_openrouter_base(cleaned_base_url) or "minimax" not in cleaned_base_url.lower():
            raise LLMProviderResolutionError(
                "Invalid config: provider=minimax cannot use OPENAI_BASE_URL unless it is a MiniMax endpoint."
            )

    if resolved_provider == "openrouter" and cleaned_base_url:
        if "openrouter.ai" not in cleaned_base_url.lower():
            raise LLMProviderResolutionError(
                "Invalid config: provider=openrouter cannot use OPENAI_BASE_URL unless it is an OpenRouter endpoint."
            )
    api_key, api_key_source = _pick_api_key(resolved_provider, env_map, configured_api_key)
    if not api_key:
        required = {
            "openrouter": "OPENROUTER_API_KEY",
            "openai": "OPENAI_API_KEY",
            "xai": "XAI_API_KEY",
            "minimax": "MINIMAX_API_KEY",
        }[resolved_provider]
        raise LLMProviderResolutionError(
            f"Missing credentials: provider={resolved_provider} requires {required}."
        )

    return ResolvedLlmProvider(
        provider=resolved_provider,
        model=resolved_model,
        base_url=selected_base_url.rstrip("/"),
        api_key=api_key,
        api_key_source=api_key_source,
    )
