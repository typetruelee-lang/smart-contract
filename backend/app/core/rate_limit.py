"""Rate limit — Redis 고정 윈도우. Redis 가 없으면 프로세스 메모리로 대체."""
from __future__ import annotations

import logging
import threading
import time

import redis

from app.core.config import get_settings

log = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._redis_checked = False
        self._mem: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def _client(self) -> redis.Redis | None:
        if not self._redis_checked:
            self._redis_checked = True
            try:
                c = redis.Redis.from_url(get_settings().REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5)
                c.ping()
                self._redis = c
            except Exception:  # noqa: BLE001
                log.warning("Redis 연결 실패 — rate limit 을 메모리 모드로 사용합니다.")
                self._redis = None
        return self._redis

    @property
    def backend(self) -> str:
        return "redis" if self._client() else "memory"

    def hit(self, key: str, limit: int, window: int = 60) -> bool:
        """True = 허용, False = 초과."""
        bucket = int(time.time() // window)
        full = f"rl:{key}:{bucket}"
        c = self._client()
        if c is not None:
            try:
                n = c.incr(full)
                if n == 1:
                    c.expire(full, window + 1)
                return n <= limit
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            b, n = self._mem.get(key, (bucket, 0))
            if b != bucket:
                b, n = bucket, 0
            n += 1
            self._mem[key] = (b, n)
            return n <= limit

    def reset(self) -> None:
        with self._lock:
            self._mem.clear()
        c = self._client()
        if c is not None:
            try:
                for k in c.scan_iter("rl:*"):
                    c.delete(k)
            except Exception:  # noqa: BLE001
                pass


limiter = RateLimiter()


def limit_for(path: str, method: str) -> tuple[str, int]:
    s = get_settings()
    if path.startswith("/api/auth/"):
        return "auth", s.RATE_LIMIT_AUTH_PER_MINUTE
    if method == "POST" and path.endswith("/upload"):
        return "upload", s.RATE_LIMIT_UPLOAD_PER_MINUTE
    if path.startswith("/api/verify"):
        return "verify", s.RATE_LIMIT_VERIFY_PER_MINUTE
    return "default", s.RATE_LIMIT_PER_MINUTE
