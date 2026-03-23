from __future__ import annotations

import hmac
import hashlib
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.lola_whatsapp_gateway.main import app
from normalize import normalize_meta_payload, normalize_twilio_payload
from provider_meta import verify_meta_signature


def test_normalize_meta_payload():
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"profile": {"name": "Matt"}}],
                    "messages": [{
                        "id": "wamid-1",
                        "from": "+15551230000",
                        "type": "text",
                        "text": {"body": "status"},
                    }],
                }
            }]
        }]
    }
    normalized = normalize_meta_payload(payload)
    assert normalized is not None
    assert normalized.provider == "meta"
    assert normalized.sender == "+15551230000"
    assert normalized.text == "status"


def test_normalize_twilio_payload():
    payload = {"From": "+15551230000", "Body": "status", "MessageSid": "SM123"}
    normalized = normalize_twilio_payload(payload)
    assert normalized is not None
    assert normalized.provider == "twilio"
    assert normalized.message_id == "SM123"


def test_verify_meta_signature():
    body = b'{"test":true}'
    secret = 'secret'
    signature = 'sha256=' + hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
    assert verify_meta_signature(body, signature, secret) is True


def test_healthz():
    client = TestClient(app)
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_meta_verify_endpoint(monkeypatch):
    monkeypatch.setenv('LOLA_META_VERIFY_TOKEN', 'verify-me')
    from config import get_config
    get_config.cache_clear()
    client = TestClient(app)
    response = client.get('/webhook', params={
        'hub.mode': 'subscribe',
        'hub.verify_token': 'verify-me',
        'hub.challenge': '12345',
    })
    assert response.status_code == 200
    assert response.text == '12345'
    get_config.cache_clear()
