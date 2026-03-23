from __future__ import annotations

import threading
import time
from collections import OrderedDict

from config import get_config

_seen: OrderedDict[str, float] = OrderedDict()
_lock = threading.Lock()
_MAX_KEYS = 5000


def is_duplicate(message_id: str) -> bool:
    if not message_id:
        return False
    now = time.monotonic()
    ttl = get_config().dedupe_ttl_seconds
    with _lock:
        cutoff = now - ttl
        while _seen and next(iter(_seen.values())) < cutoff:
            _seen.popitem(last=False)
        if message_id in _seen:
            return True
        if len(_seen) >= _MAX_KEYS:
            _seen.popitem(last=False)
        _seen[message_id] = now
        return False
