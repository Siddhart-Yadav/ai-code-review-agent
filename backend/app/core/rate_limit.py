"""
Simple in-memory rate limiter for deployed usage.

Limits reviews per IP to prevent abuse of hosted Groq API key.
Resets automatically — no Redis dependency required.
"""

import time
import logging
from collections import defaultdict

from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token-bucket style rate limiter keyed by client IP."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        """Raise 429 if the client has exceeded the rate limit."""
        ip = self._get_client_ip(request)
        now = time.time()
        cutoff = now - self.window_seconds

        # Prune old entries
        self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]

        if len(self._requests[ip]) >= self.max_requests:
            remaining = int(self._requests[ip][0] + self.window_seconds - now)
            logger.warning("Rate limit exceeded for %s (%d requests)", ip, len(self._requests[ip]))
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {self.max_requests} reviews per hour. "
                       f"Try again in {remaining // 60} minutes.",
            )

        self._requests[ip].append(now)


# Singleton — 5 reviews per hour per IP
review_rate_limiter = RateLimiter(max_requests=5, window_seconds=3600)
