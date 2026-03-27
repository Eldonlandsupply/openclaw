"""
Reusable Telegram payload fixtures for tests.

Usage:
    from tests.fixtures.telegram_payloads import (
        make_text_update,
        make_command_update,
        make_unauthorized_update,
        make_empty_text_update,
        make_edited_message_update,
        make_callback_query_update,
    )
"""

from __future__ import annotations


def make_text_update(
    chat_id: int = 7828643627,
    text: str = "Hello Lola",
    update_id: int = 1001,
    user_id: int = 12345,
    username: str = "testuser",
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": user_id, "is_bot": False, "username": username},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            "text": text,
        },
    }


def make_command_update(
    chat_id: int = 7828643627,
    command: str = "/start",
    update_id: int = 1002,
) -> dict:
    return make_text_update(chat_id=chat_id, text=command, update_id=update_id)


def make_unauthorized_update(
    chat_id: int = 9999999,
    text: str = "who are you",
    update_id: int = 1003,
) -> dict:
    return make_text_update(chat_id=chat_id, text=text, update_id=update_id)


def make_empty_text_update(
    chat_id: int = 7828643627,
    update_id: int = 1004,
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": 12345, "is_bot": False},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            # No "text" key — e.g. a sticker or photo
        },
    }


def make_edited_message_update(
    chat_id: int = 7828643627,
    text: str = "edited message",
    update_id: int = 1005,
) -> dict:
    return {
        "update_id": update_id,
        "edited_message": {
            "message_id": 500,
            "from": {"id": 12345, "is_bot": False},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            "text": text,
        },
    }


def make_callback_query_update(
    chat_id: int = 7828643627,
    data: str = "action:approve",
    update_id: int = 1006,
) -> dict:
    """Callback query (inline keyboard button press) — no message key."""
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cq001",
            "from": {"id": 12345, "is_bot": False},
            "message": {
                "message_id": 50,
                "chat": {"id": chat_id, "type": "private"},
            },
            "data": data,
        },
    }


def make_malformed_update(update_id: int = 1007) -> dict:
    """Update missing required nested fields."""
    return {"update_id": update_id, "message": {}}


def make_getme_response(username: str = "tynskieldonbot", bot_id: int = 7777777) -> dict:
    return {
        "ok": True,
        "result": {
            "id": bot_id,
            "is_bot": True,
            "first_name": "Lola",
            "username": username,
        },
    }


def make_getupdates_response(updates: list[dict]) -> dict:
    return {"ok": True, "result": updates}


def make_getupdates_error_response() -> dict:
    return {"ok": False, "description": "Unauthorized", "error_code": 401}


def make_sendmessage_ok_response() -> dict:
    return {"ok": True, "result": {"message_id": 999}}


def make_sendmessage_error_response(status: int = 400) -> dict:
    return {"ok": False, "description": "Bad Request: chat not found", "error_code": status}
