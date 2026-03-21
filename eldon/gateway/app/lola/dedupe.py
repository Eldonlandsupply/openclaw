"""Lola dedupe guard — prevents duplicate WhatsApp webhook deliveries."""

from __future__ import annotations
import os, threading, time
from collections import OrderedDict

_TTL = int(os.getenv("LOLA_DEDUPE_TTL_SECONDS", "600"))
_MAX = 5000
_store: OrderedDict = OrderedDict()
_lock = threading.Lock()


def is_duplicate(message_id: str) -> bool:
    now = time.monotonic()
    with _lock:
        cutoff = now - _TTL
        while _store and next(iter(_store.values())) < cutoff:
            _store.popitem(last=False)
        if message_id in _store:
            return True
        if len(_store) >= _MAX:
            _store.popitem(last=False)
        _store[message_id] = now
        return False
