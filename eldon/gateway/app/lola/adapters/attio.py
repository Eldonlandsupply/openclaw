"""
Lola Attio adapter — read and approval-gated write via existing Attio client.
"""

from __future__ import annotations

import os
import sys

# Reach the existing Attio client from the eldon src tree
_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

try:
    from openclaw.integrations.attio.client import AttioClient
    _ATTIO_AVAILABLE = True
except ImportError:
    _ATTIO_AVAILABLE = False

_ATTIO_API_KEY = os.getenv("ATTIO_API_KEY", "")


def _client() -> "AttioClient":
    if not _ATTIO_AVAILABLE:
        raise RuntimeError("Attio client not importable. Ensure eldon/src is in PYTHONPATH.")
    if not _ATTIO_API_KEY:
        raise RuntimeError("ATTIO_API_KEY not set.")
    return AttioClient(api_key=_ATTIO_API_KEY)


async def search_contacts(query: str, limit: int = 5) -> list[dict]:
    """Search Attio people records. Read-only, auto-execute."""
    if not _ATTIO_API_KEY:
        return [{"error": "ATTIO_API_KEY not configured"}]
    try:
        c = _client()
        results = await c.search_records("people", query, limit=limit)
        await c.close()
        contacts = []
        for r in results:
            attrs = r.get("values", {})
            name = attrs.get("name", [{}])[0].get("full_name", "") if attrs.get("name") else ""
            email = attrs.get("email_addresses", [{}])[0].get("email_address", "") if attrs.get("email_addresses") else ""
            contacts.append({"id": r.get("id", {}).get("record_id", ""), "name": name, "email": email})
        return contacts
    except Exception as e:
        return [{"error": str(e)}]


async def search_companies(query: str, limit: int = 5) -> list[dict]:
    """Search Attio company records. Read-only, auto-execute."""
    if not _ATTIO_API_KEY:
        return [{"error": "ATTIO_API_KEY not configured"}]
    try:
        c = _client()
        results = await c.search_records("companies", query, limit=limit)
        await c.close()
        companies = []
        for r in results:
            attrs = r.get("values", {})
            name = attrs.get("name", [{}])[0].get("value", "") if attrs.get("name") else ""
            domain = attrs.get("domains", [{}])[0].get("domain", "") if attrs.get("domains") else ""
            companies.append({"id": r.get("id", {}).get("record_id", ""), "name": name, "domain": domain})
        return companies
    except Exception as e:
        return [{"error": str(e)}]


async def add_note_to_record(object_type: str, record_id: str, title: str, body: str) -> dict:
    """Add a note to a record. Requires prior approval — caller must verify."""
    if not _ATTIO_API_KEY:
        return {"error": "ATTIO_API_KEY not configured"}
    try:
        c = _client()
        result = await c._post("/notes", {
            "data": {
                "parent_object": object_type,
                "parent_record_id": record_id,
                "title": title,
                "content": {"document": {"schema": "2", "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}]}},
            }
        })
        await c.close()
        return {"success": True, "note_id": result.get("data", {}).get("id", {}).get("note_id", "")}
    except Exception as e:
        return {"error": str(e)}


def format_contacts_for_lola(contacts: list[dict]) -> str:
    if not contacts:
        return "No matching contacts found."
    if "error" in contacts[0]:
        return f"Attio unavailable: {contacts[0]['error']}"
    lines = []
    for c in contacts:
        lines.append(f"• {c['name']} — {c['email']} (ID: {c['id'][:8]}...)")
    return "\n".join(lines)
