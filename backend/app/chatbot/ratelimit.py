"""Tiny in-process sliding-window rate limiter.

Chatbot-scoped on purpose: when the backend lead's shared/Redis-backed limiter for
the whole API lands, swap ``check_rate_limit`` behind the same signature (§12 of
the contract).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Tuple


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


DEFAULT_SESSION_RULE = RateLimitRule("session_per_ip", 10, 3600)
DEFAULT_MESSAGE_RULE = RateLimitRule("messages_per_session", 30, 60)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__("rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class RateLimiter:
    def __init__(self) -> None:
        self._hits: Dict[Tuple[str, str], Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, rule: RateLimitRule, key: str) -> None:
        """Raise RateLimitExceeded when the key exhausted its quota."""
        now = time.monotonic()
        bucket_key = (rule.name, key)
        with self._lock:
            bucket = self._hits.setdefault(bucket_key, deque())
            while bucket and now - bucket[0] > rule.window_seconds:
                bucket.popleft()
            if len(bucket) >= rule.limit:
                retry_after = int(rule.window_seconds - (now - bucket[0])) + 1
                raise RateLimitExceeded(max(retry_after, 1))
            bucket.append(now)

    def reset(self) -> None:  # used by tests
        with self._lock:
            self._hits.clear()
