---
name: openclaw-setup
description: >
  Deterministic setup guide for Openclaw (Python AI agent runtime). Use this skill whenever
  setting up Openclaw from scratch, configuring .env + config.yaml, running the doctor sanity
  check, or troubleshooting common misconfigurations (placeholder model IDs, memory/embedding
  conflicts, committed secrets). Also use when creating or validating the config schema
  (src/config/schema.py, src/config/loader.py) or the scripts/doctor.py bootstrap script.
---

# Openclaw Setup (Deterministic)

This skill captures the canonical, repeatable process for setting up Openclaw on a new machine
(Windows/PowerShell reference), configuring it correctly, and verifying the config before
first run.

---

## Configuration model

Openclaw reads from two sources — never mix them:

| Source | Contains |
|--------|----------|
| `config.yaml` | Non-secret settings; uses `${VAR}` / `${VAR:default}` interpolation |
| `.env` | Secrets and env overrides; **never commit this file** |

**Hard rule**: only `.env.example` is committed to the repo. `.env` is in `.gitignore`.

---

## Required files

### 1. `requirements.txt` additions

```
pydantic>=2.6
PyYAML>=6.0
```

### 2. `src/config/schema.py`

```python
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


PLACEHOLDER_VALUES = {"YOUR_CHAT_MODEL", "YOUR_EMBED_MODEL", "CHANGE_ME", "TODO"}


class AppConfig(BaseModel):
    env: str = Field(default="development")
    log_level: str = Field(default="info")


class LLMConfig(BaseModel):
    chat_model: str = Field(..., min_length=1)
    embedding_model: Optional[str] = Field(default=None)

    @field_validator("chat_model")
    @classmethod
    def validate_chat_model(cls, v: str) -> str:
        vv = v.strip()
        if not vv:
            raise ValueError("llm.chat_model cannot be empty")
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
    llm: LLMConfig
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    @model_validator(mode="after")
    def cross_field_gates(self) -> "Settings":
        if self.memory.enabled:
            if not self.llm.embedding_model:
                raise ValueError(
                    "Memory is enabled but llm.embedding_model is not set. "
                    "Set YOUR_EMBED_MODEL (e.g. text-embedding-3-small) or disable memory."
                )
        return self
```

### 3. `src/config/loader.py`

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .schema import Settings


def _expand_env_token(token: str) -> str:
    inner = token[2:-1]
    if ":" in inner:
        var, default = inner.split(":", 1)
        return os.getenv(var, default)
    return os.getenv(inner, "")


def _walk_expand(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _walk_expand(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_expand(v) for v in obj]
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("${") and s.endswith("}"):
            return _expand_env_token(s)
        return obj
    return obj


def load_settings(config_path: str = "config.yaml") -> Settings:
    p = Path(config_path)
    if not p.exists():
        raise RuntimeError(
            f"Missing {config_path}. Create it or copy from a template. "
            f"Expected at repo root: {p.resolve()}"
        )

    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    expanded = _walk_expand(raw)

    try:
        return Settings.model_validate(expanded)
    except Exception as e:
        raise RuntimeError(f"Config validation failed: {e}") from e
```

### 4. `scripts/doctor.py`

```python
from __future__ import annotations

from src.config.loader import load_settings


def main() -> None:
    s = load_settings()
    print("OK config loaded")
    print(f"chat_model={s.llm.chat_model}")
    print(f"embedding_model={s.llm.embedding_model or '(none)'}")
    print(f"memory_enabled={s.memory.enabled}")
    print(f"vector_store={s.memory.vector_store}")
    print(f"vector_store_path={s.memory.vector_store_path}")


if __name__ == "__main__":
    main()
```

### 5. `config.yaml` (repo root)

```yaml
app:
  env: ${ENV:development}
  log_level: ${LOG_LEVEL:info}

llm:
  chat_model: ${YOUR_CHAT_MODEL}
  embedding_model: ${YOUR_EMBED_MODEL:}

memory:
  enabled: ${ENABLE_MEMORY:false}
  vector_store: ${VECTOR_STORE:local}
  vector_store_path: ${VECTOR_STORE_PATH:.data/vector_store}
```

### 6. `.env.example` (commit this, not `.env`)

```env
# Required
OPENAI_API_KEY=sk-...
YOUR_CHAT_MODEL=gpt-5-nano

# Optional — only needed when memory.enabled=true
# YOUR_EMBED_MODEL=text-embedding-3-small

# Optional overrides
# ENABLE_MEMORY=false
# ENV=development
# LOG_LEVEL=info
```

### 7. `.gitignore` (minimum required entries)

```
.env
.data/
__pycache__/
.venv/
*.log
```

---

## Setup procedure (PowerShell)

```powershell
git clone <REPO_URL>
cd <REPO_FOLDER>

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

copy .env.example .env
notepad .env
# Set OPENAI_API_KEY and YOUR_CHAT_MODEL — remove all placeholders

python .\scripts\doctor.py
```

Expected doctor output:

```
OK config loaded
chat_model=gpt-5-nano
embedding_model=(none)
memory_enabled=False
vector_store=local
vector_store_path=.data/vector_store
```

---

## Recommended model IDs

| Use case | Model |
|----------|-------|
| Most efficient | `gpt-5-nano` |
| More capable / efficient | `gpt-5-mini` |
| Embeddings | `text-embedding-3-small` |

---

## Common misconfigurations

### App still shows `YOUR_CHAT_MODEL`

Cause: placeholder never replaced in `.env`, or `config.yaml` is not using `${YOUR_CHAT_MODEL}`.

Fix:
1. Set `YOUR_CHAT_MODEL=gpt-5-nano` in `.env`
2. Confirm `config.yaml` has `chat_model: ${YOUR_CHAT_MODEL}`

### Memory enabled but embeddings missing

Cause: `ENABLE_MEMORY=true` but `YOUR_EMBED_MODEL` is blank.

Fix: Set `YOUR_EMBED_MODEL=text-embedding-3-small` in `.env`, or set `ENABLE_MEMORY=false`.

### Secrets accidentally committed

Fix immediately:
1. Remove secrets from git history
2. Rotate all compromised keys
3. Confirm `.gitignore` includes `.env`

---

## Fail-fast gates (doctor enforces these)

| Condition | Error |
|-----------|-------|
| `YOUR_CHAT_MODEL` still placeholder | `llm.chat_model is still a placeholder` |
| `YOUR_EMBED_MODEL` still placeholder | `llm.embedding_model is still a placeholder` |
| `memory.enabled=true` + no embed model | `Memory is enabled but llm.embedding_model is not set` |
| `config.yaml` missing | `Missing config.yaml` |

---

## Startup verification

After `python -m openclaw`:
- Logs must show the resolved `chat_model`
- If memory is enabled, logs must show the `embedding_model`
