"""A simple rate limiter that keeps its counts in memory."""

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """Allow at most `limit` requests per visitor in `window` seconds.

    Counts are kept in memory, so this only works for a single server process.
    """

    def __init__(self, limit: int, window: float = 60.0) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client: str) -> float:
        """Count a request. Returns 0 if it is allowed, or how many seconds to wait if not."""
        now = time.monotonic()
        hits = self._hits[client]
        while hits and now - hits[0] > self.window:  # forget requests that are too old
            hits.popleft()
        if len(hits) >= self.limit:
            return self.window - (now - hits[0])
        hits.append(now)
        return 0.0
