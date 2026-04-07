import time
from collections import deque
from .config import MessagingConfig


class MessagePolicy:
    def __init__(self, config: MessagingConfig):
        self.config = config
        self._send_times: deque = deque()
        self._recent_hashes: dict[str, float] = {}

    def _hash(self, recipient: str, body: str) -> str:
        return f"{recipient}::{body}"

    def allow(self, recipient: str, body: str) -> tuple[bool, str]:
        if self.config.kill_switch:
            return False, "kill switch is active"
        if not self.config.enabled:
            return False, "messaging disabled"
        if recipient not in self.config.allowed_recipients:
            return False, f"{recipient} not in allowlist"
        now = time.time()
        cutoff = now - 3600
        while self._send_times and self._send_times[0] < cutoff:
            self._send_times.popleft()
        if len(self._send_times) >= self.config.rate_limit_per_hour:
            return False, "rate limit exceeded"
        self._prune_recent_hashes(now)
        h = self._hash(recipient, body)
        last_sent = self._recent_hashes.get(h, 0)
        if now - last_sent < self.config.dedup_window_minutes * 60:
            return False, "duplicate suppressed"
        return True, "ok"

    def _prune_recent_hashes(self, now: float) -> None:
        dedup_cutoff = now - (self.config.dedup_window_minutes * 60)
        self._recent_hashes = {
            message_hash: sent_at
            for message_hash, sent_at in self._recent_hashes.items()
            if sent_at >= dedup_cutoff
        }

    def record_send(self, recipient: str, body: str):
        now = time.time()
        self._prune_recent_hashes(now)
        self._send_times.append(now)
        self._recent_hashes[self._hash(recipient, body)] = now
