from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet


@dataclass(frozen=True)
class GatewayConfig:
    app_host: str
    app_port: int
    provider: str
    meta_verify_token: str
    meta_app_secret: str
    meta_api_version: str
    meta_phone_number_id: str
    meta_access_token: str
    twilio_auth_token: str
    twilio_account_sid: str
    twilio_messaging_service_sid: str
    twilio_from_number: str
    dedupe_ttl_seconds: int
    allowed_senders: FrozenSet[str]


@lru_cache(maxsize=1)
def get_config() -> GatewayConfig:
    return GatewayConfig(
        app_host=os.getenv("LOLA_GATEWAY_HOST", "0.0.0.0"),
        app_port=int(os.getenv("LOLA_GATEWAY_PORT", "8080")),
        provider=os.getenv("LOLA_WHATSAPP_PROVIDER", "auto").strip().lower(),
        meta_verify_token=os.getenv("LOLA_META_VERIFY_TOKEN", ""),
        meta_app_secret=os.getenv("LOLA_META_APP_SECRET", ""),
        meta_api_version=os.getenv("LOLA_META_API_VERSION", "v19.0"),
        meta_phone_number_id=os.getenv("LOLA_META_PHONE_NUMBER_ID", ""),
        meta_access_token=os.getenv("LOLA_META_ACCESS_TOKEN", ""),
        twilio_auth_token=os.getenv("LOLA_TWILIO_AUTH_TOKEN", ""),
        twilio_account_sid=os.getenv("LOLA_TWILIO_ACCOUNT_SID", ""),
        twilio_messaging_service_sid=os.getenv("LOLA_TWILIO_MESSAGING_SERVICE_SID", ""),
        twilio_from_number=os.getenv("LOLA_TWILIO_FROM_NUMBER", ""),
        dedupe_ttl_seconds=int(os.getenv("LOLA_DEDUPE_TTL_SECONDS", "600")),
        allowed_senders=frozenset(
            item.strip() for item in os.getenv("LOLA_ALLOWED_SENDERS", "").split(",") if item.strip()
        ),
    )
