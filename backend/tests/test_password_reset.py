from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import auth as auth_module
from app.core.config import settings
from app.models.user import PasswordResetToken


@pytest.mark.asyncio
async def test_reset_is_neutral_one_time_and_revokes_sessions(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    delivered = []
    async def capture(email, url):
        delivered.append((email, url))
    monkeypatch.setattr(auth_module, "deliver_password_reset", capture)
    registered = await client.post("/api/v1/auth/register", json={"email": "reset@example.com", "password": "OldPassword123!", "full_name": "Reset User"})
    assert registered.status_code == 200
    old_access = registered.json()["data"]["token"]["access_token"]
    unknown = await client.post("/api/v1/auth/password-reset/request", json={"email": "unknown@example.com"})
    known = await client.post("/api/v1/auth/password-reset/request", json={"email": "RESET@example.com"})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json()["data"] == known.json()["data"]
    assert len(delivered) == 1 and delivered[0][0] == "reset@example.com"
    token = parse_qs(urlparse(delivered[0][1]).fragment)["token"][0]
    stored = (await db_session.execute(select(PasswordResetToken))).scalar_one()
    assert token not in stored.token_hash and len(stored.token_hash) == 64
    reset = await client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": "NewPassword123!"})
    assert reset.status_code == 200
    assert (await client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": "OtherPassword123!"})).status_code == 400
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": "OldPassword123!"})).status_code == 401
    assert (await client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": "NewPassword123!"})).status_code == 200


@pytest.mark.asyncio
async def test_reset_expiry_and_second_request_invalidate_first(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    links = []
    async def capture(email, url): links.append(url)
    monkeypatch.setattr(auth_module, "deliver_password_reset", capture)
    await client.post("/api/v1/auth/register", json={"email": "expiry@example.com", "password": "OldPassword123!", "full_name": "Expiry User"})
    for _ in range(2):
        assert (await client.post("/api/v1/auth/password-reset/request", json={"email": "expiry@example.com"})).status_code == 200
    first = parse_qs(urlparse(links[0]).fragment)["token"][0]
    second = parse_qs(urlparse(links[1]).fragment)["token"][0]
    assert (await client.post("/api/v1/auth/password-reset/confirm", json={"token": first, "password": "NewPassword123!"})).status_code == 400
    token_id = second.split(".", 1)[0]
    stored = (await db_session.execute(select(PasswordResetToken).where(PasswordResetToken.id == token_id))).scalar_one()
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    assert (await client.post("/api/v1/auth/password-reset/confirm", json={"token": second, "password": "NewPassword123!"})).status_code == 400


@pytest.mark.asyncio
async def test_reset_request_rate_limited(client: AsyncClient):
    for index in range(settings.RATE_LIMIT_PASSWORD_RESET_PER_HOUR):
        response = await client.post("/api/v1/auth/password-reset/request", json={"email": f"nope{index}@example.com"})
        assert response.status_code == 200
    blocked = await client.post("/api/v1/auth/password-reset/request", json={"email": "another@example.com"})
    assert blocked.status_code == 429
