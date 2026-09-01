import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) >= limit:
                raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")
            events.append(now)


limiter = SlidingWindowLimiter()


def request_key(request: Request, user_id: str | None, action: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{action}:{user_id or host}"

