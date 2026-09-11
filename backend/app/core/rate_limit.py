"""Database-backed fixed-window controls shared by all API workers."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import RateLimitBucket

def client_ip(request: Request) -> str:
    # Only the directly connected address is trusted. A deployment may replace
    # this at a trusted proxy boundary; arbitrary X-Forwarded-For is ignored.
    return request.client.host if request.client else "unknown"

async def enforce_rate_limit(db: AsyncSession, *, key: str, limit: int, window_seconds: int) -> None:
    now = datetime.now(timezone.utc)
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
    bucket = (await db.execute(select(RateLimitBucket).where(RateLimitBucket.key == key).with_for_update())).scalar_one_or_none()
    if bucket is None:
        db.add(RateLimitBucket(key=key, window_started_at=now, request_count=1))
        await db.commit()
        return
    started = bucket.window_started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if now - started >= timedelta(seconds=window_seconds):
        bucket.window_started_at, bucket.request_count = now, 1
        await db.commit()
        return
    if bucket.request_count >= limit:
        retry_after = max(1, int(window_seconds - (now - started).total_seconds()))
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Request rate limit exceeded.", headers={"Retry-After": str(retry_after)})
    bucket.request_count += 1
    await db.commit()
