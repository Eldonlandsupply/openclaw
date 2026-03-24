# Lola Executive Assistant

Standalone FastAPI service. Lola is the executive assistant for Matthew Tynski.

## Endpoints

- `GET /healthz` - health check
- `GET /inbox` - raw inbox summary
- `GET /calendar` - upcoming events
- `GET /briefing` - full morning briefing via LLM
- `POST /webhook` - WhatsApp/Twilio inbound (TwiML response)
- `POST /command` - direct JSON command {"message": "..."}

## Required env vars

AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
OUTLOOK_USER=tynski@eldonlandsupply.com
OPENROUTER_API_KEY
LOLA_ALLOWED_NUMBERS=17087525462
LOLA_MODEL=openai/gpt-4o-mini

## Run

cd apps/lola_whatsapp_gateway
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8090

