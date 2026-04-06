from __future__ import annotations

import os
import re
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

# Canonical env var name per provider. Never infer provider from generic OPENAI_* vars.
_PROVIDER_KEY_VAR: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
}

# Regex that matches <think>...</think> blocks, including multiline and nested tags.
# MiniMax-Text-01 and MiniMax-M1 embed chain-of-thought inside the content field
# using these tags. They must be stripped before the reply is returned to the user.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning_tags(text: str) -> str:
    """
    Remove <think>...</think> reasoning blocks from LLM output.

    MiniMax (and some other reasoning models) embed chain-of-thought in the
    content field as <think>...</think>. This function strips all such blocks
    and collapses any leading whitespace left behind.

    Safe to call on any provider output — no-op if no tags are present.
    """
    cleaned = _THINK_RE.sub("", text)
    return cleaned.strip()


def _normalize_provider(provider: str | None) -> str:
    return (provider or "none").strip().lower()


def _looks_like_openrouter_base(url: str | None) -> bool:
    if not url:
        return False
    return "openrouter.ai" in url.strip().lower()


def _pick_api_key(
    provider: str, env: Mapping[str, str], explicit: str | None
) -> tuple[str, str]:
    if explicit and explicit.strip():
        return explicit.strip(), "config"
    env_var = _PROVIDER_KEY_VAR.get(provider)
    if not env_var:
        return "", "none"
    value = (env.get(env_var) or "").strip()
    return value, (f"env:{env_var}" if value else "none")


def _check_contradictory_env(provider: str, env: Mapping[str, str]) -> None:
    """
    Raise if environment contains keys for a DIFFERENT provider than the one
    selected, AND the selected provider's key is missing.
    This catches the silent-routing-to-wrong-provider failure mode.
    """
    if provider not in _PROVIDER_KEY_VAR:
        return
    my_var = _PROVIDER_KEY_VAR[provider]
    my_key = (env.get(my_var) or "").strip()
    if my_key:
        return  # correct key present — no contradiction

    # My key is missing. Check if a different provider's key is present.
    for other_provider, other_var in _PROVIDER_KEY_VAR.items():
        if other_provider == provider:
            continue
        if (env.get(other_var) or "").strip():
            raise LLMProviderResolutionError(
                f"Contradictory config: LLM_PROVIDER={provider!r} but "
                f"{my_var} is not set while {other_var} ({other_provider}) is present. "
                f"Set {my_var} in /etc/openclaw/openclaw.env or update LLM_PROVIDER."
            )


def resolve_llm_provider(
    *,
    provider: str,
    model: str,
    configured_base_url: str | None = None,
    configured_api_key: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedLlmProvider:
    """
    Deterministically resolve the LLM provider configuration.

    Rules:
    - provider is always taken from the explicit argument (from LLM_PROVIDER env var
      via config.yaml expansion). It is NEVER inferred from OPENAI_BASE_URL or
      from which API keys happen to be present.
    - Each provider has a canonical base URL. Only provider=openai allows
      OPENAI_BASE_URL to override (for local/self-hosted deployments).
    - If provider=minimax, any non-MiniMax base_url is rejected.
    - If provider=openrouter, any non-OpenRouter base_url is rejected.
    - If the selected provider's key is absent but another provider's key is
      present, a LLMProviderResolutionError is raised (contradictory env).
    - If the key is simply absent, a LLMProviderResolutionError is raised.
    """
    resolved_provider = _normalize_provider(provider)
    resolved_model = (model or "").strip()
    env_map = env if env is not None else dict(os.environ)

    if resolved_provider not in {"openrouter", "openai", "xai", "minimax", "none"}:
        raise LLMProviderResolutionError(
            f"Unsupported provider: {resolved_provider!r}. "
            f"Valid values: openrouter, openai, xai, minimax, none"
        )

    if resolved_provider == "none":
        return ResolvedLlmProvider(
            provider="none",
            model=resolved_model,
            base_url="",
            api_key="",
            api_key_source="none",
        )

    cleaned_base_url = (configured_base_url or "").strip()

    # Canonical base URL — only openai allows override via OPENAI_BASE_URL
    if resolved_provider == "openai":
        selected_base_url = cleaned_base_url or _PROVIDER_BASE_URLS[resolved_provider]
    else:
        selected_base_url = _PROVIDER_BASE_URLS[resolved_provider]

    # Explicit contradiction checks: reject mismatched base URLs
    if resolved_provider == "minimax" and cleaned_base_url:
        if (
            _looks_like_openrouter_base(cleaned_base_url)
            or "minimax" not in cleaned_base_url.lower()
        ):
            raise LLMProviderResolutionError(
                f"Invalid config: provider=minimax cannot use base_url={cleaned_base_url!r}. "
                f"The base URL must be a MiniMax endpoint."
            )

    if resolved_provider == "openrouter" and cleaned_base_url:
        if "openrouter.ai" not in cleaned_base_url.lower():
            raise LLMProviderResolutionError(
                f"Invalid config: provider=openrouter cannot use base_url={cleaned_base_url!r}. "
                f"The base URL must be an OpenRouter endpoint."
            )

    # Contradiction check: selected provider key missing but another provider's key present
    _check_contradictory_env(resolved_provider, env_map)

    api_key, api_key_source = _pick_api_key(
        resolved_provider, env_map, configured_api_key
    )
    if not api_key:
        required = _PROVIDER_KEY_VAR[resolved_provider]
        raise LLMProviderResolutionError(
            f"Missing credentials: provider={resolved_provider!r} requires {required} "
            f"to be set in /etc/openclaw/openclaw.env."
        )

    return ResolvedLlmProvider(
        provider=resolved_provider,
        model=resolved_model,
        base_url=selected_base_url.rstrip("/"),
        api_key=api_key,
        api_key_source=api_key_source,
    )
