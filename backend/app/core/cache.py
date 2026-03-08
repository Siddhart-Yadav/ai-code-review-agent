import hashlib
import json

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


def compute_diff_hash(diff_content: str) -> str:
    return hashlib.sha256(diff_content.encode()).hexdigest()


async def get_cached_review(diff_hash: str) -> dict | None:
    cached = await redis_client.get(f"review:{diff_hash}")
    if cached:
        return json.loads(cached)
    return None


async def set_cached_review(diff_hash: str, review: dict) -> None:
    await redis_client.set(
        f"review:{diff_hash}",
        json.dumps(review),
        ex=settings.CACHE_TTL_SECONDS,
    )


async def invalidate_review(diff_hash: str) -> None:
    await redis_client.delete(f"review:{diff_hash}")
