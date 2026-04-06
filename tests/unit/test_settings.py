from __future__ import annotations

from openclaw.settings import get_settings


def test_settings_loads_openclaw_app_name(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_ENV", "test")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.runtime.app.app_name == "openclaw"
