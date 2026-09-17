from datetime import datetime, timedelta, timezone
import uuid
import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.models.user import RefreshToken, UserSession

async def register(client: AsyncClient, suffix: str = "one"):
    return await client.post("/api/v1/auth/register", json={"email": f"phase6-{suffix}@example.com", "password": "DefensiblePass123!", "full_name": "Phase Six"})

@pytest.mark.asyncio
async def test_short_access_token_contains_minimal_session_claims(client: AsyncClient):
    response = await register(client); assert response.status_code == 200
    token = response.json()["data"]["token"]["access_token"]; payload = decode_access_token(token)
    assert {"sub", "sid", "jti", "iat", "exp", "typ"} <= payload.keys()
    assert payload["typ"] == "access" and payload["exp"] - payload["iat"] <= 15 * 60 + 1

@pytest.mark.asyncio
async def test_refresh_rotates_hash_and_replay_revokes_session(client: AsyncClient, db_session: AsyncSession):
    response = await register(client, "rotate"); old_cookie = response.cookies[settings.REFRESH_COOKIE_NAME]
    first = await client.post("/api/v1/auth/refresh"); assert first.status_code == 200
    new_cookie = first.cookies[settings.REFRESH_COOKIE_NAME]; assert new_cookie != old_cookie
    old_id = uuid.UUID(old_cookie.split(".", 1)[0]); row = (await db_session.execute(select(RefreshToken).where(RefreshToken.id == old_id))).scalar_one(); assert row.consumed_at is not None
    client.cookies.set(settings.REFRESH_COOKIE_NAME, old_cookie, path=f"{settings.API_V1_PREFIX}/auth")
    replay = await client.post("/api/v1/auth/refresh"); assert replay.status_code == 401
    session = (await db_session.execute(select(UserSession).where(UserSession.id == row.session_id))).scalar_one(); assert session.revoked_at is not None

@pytest.mark.asyncio
async def test_logout_revokes_refresh_and_access_session(client: AsyncClient):
    response = await register(client, "logout"); access = response.json()["data"]["token"]["access_token"]
    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})).status_code == 401

@pytest.mark.asyncio
async def test_expired_and_malformed_access_tokens_rejected(client: AsyncClient, test_user, db_session: AsyncSession):
    now = datetime.now(timezone.utc); session = UserSession(user_id=test_user.id, expires_at=now + timedelta(days=1), last_used_at=now); db_session.add(session); await db_session.commit()
    expired = create_access_token(test_user.id, session.id, timedelta(seconds=-1))
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer malformed"})).status_code == 401

@pytest.mark.asyncio
async def test_login_rate_limit_and_window_state_persist(client: AsyncClient):
    for _ in range(settings.RATE_LIMIT_LOGIN_PER_5_MINUTES):
        response = await client.post("/api/v1/auth/login", json={"email": "absent@example.com", "password": "wrong"})
        assert response.status_code == 401
    blocked = await client.post("/api/v1/auth/login", json={"email": "absent@example.com", "password": "wrong"})
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers

@pytest.mark.asyncio
async def test_cors_and_security_headers(client: AsyncClient):
    allowed = await client.options("/api/v1/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    denied = await client.options("/api/v1/health", headers={"Origin": "https://attacker.invalid", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in denied.headers
    response = await client.get("/api/v1/health"); assert response.headers["x-content-type-options"] == "nosniff" and response.headers["x-frame-options"] == "DENY" and response.headers.get("x-request-id")

@pytest.mark.asyncio
async def test_refresh_rejects_untrusted_browser_origin(client: AsyncClient):
    await register(client, "csrf")
    response = await client.post("/api/v1/auth/refresh", headers={"Origin": "https://attacker.invalid"})
    assert response.status_code == 403

def test_production_configuration_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production"); monkeypatch.setattr(settings, "SECRET_KEY", None)
    with pytest.raises(ValueError): settings.validate_production_configuration()

def test_production_rejects_insecure_cookie(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production"); monkeypatch.setattr(settings, "SECRET_KEY", "s" * 40)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://db/app"); monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://app.example.com"])
    monkeypatch.setattr(settings, "SANDBOX_EXECUTION_MODE", "remote"); monkeypatch.setattr(settings, "SANDBOX_RUNNER_URL", "https://runner.internal"); monkeypatch.setattr(settings, "SANDBOX_RUNNER_TOKEN", "r" * 32)
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    with pytest.raises(ValueError, match="COOKIE_SECURE"): settings.validate_production_configuration()


def test_explicit_http_deployment_requires_http_origin_and_insecure_cookie(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", "s" * 40)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://db/app")
    monkeypatch.setattr(settings, "SANDBOX_EXECUTION_MODE", "remote")
    monkeypatch.setattr(settings, "SANDBOX_RUNNER_URL", "http://sandbox-runner:9100")
    monkeypatch.setattr(settings, "SANDBOX_RUNNER_TOKEN", "r" * 32)
    monkeypatch.setattr(settings, "ALLOW_INSECURE_HTTP", True)
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["http://203.0.113.10"])
    settings.validate_production_configuration()
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://example.com"])
    with pytest.raises(ValueError, match="HTTP origins"):
        settings.validate_production_configuration()

def test_sse_route_has_no_query_token_contract():
    import inspect
    from app.api.v1.investigations import stream_investigation_events
    assert "token" not in inspect.signature(stream_investigation_events).parameters


@pytest.mark.asyncio
async def test_sse_releases_database_before_waiting_on_client():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from app.api.v1.investigations import stream_investigation_events

    investigation_id = uuid.uuid4()
    event = SimpleNamespace(id=uuid.uuid4(), event_type="closure.probe", entity_id=None,
                            payload={"sequence": 1}, created_at=datetime.now(timezone.utc))
    investigation = MagicMock()
    investigation.scalar_one_or_none.return_value = SimpleNamespace(workspace_id=uuid.uuid4())
    membership = MagicMock()
    membership.scalar_one_or_none.return_value = object()
    batch = MagicMock()
    batch.scalars.return_value.all.return_value = [event]
    db = AsyncMock()
    db.execute.side_effect = [investigation, membership, batch]
    request = SimpleNamespace(headers={}, is_disconnected=AsyncMock(return_value=False))
    response = await stream_investigation_events(investigation_id, request, SimpleNamespace(id=uuid.uuid4()), db)
    assert db.close.await_count == 1
    generator = response.body_iterator
    try:
        assert "connected" in await anext(generator)
        assert str(event.id) in await anext(generator)
        # The generator is suspended on client consumption with no checked-out DB connection.
        assert db.close.await_count == 2
    finally:
        await generator.aclose()


@pytest.mark.asyncio
async def test_broadcaster_detaches_full_queue_without_blocking_fast_client():
    from app.agent.sse_manager import SSEBroadcaster
    broadcaster = SSEBroadcaster()
    slow = broadcaster.subscribe("bounded")
    fast = broadcaster.subscribe("bounded")
    for i in range(1000):
        await broadcaster.emit("bounded", "probe", {"sequence": i})
        assert f'"sequence": {i}' in fast.get_nowait()
    assert slow.qsize() == slow.maxsize == 100
    assert slow not in broadcaster._subscribers["bounded"]


@pytest.mark.asyncio
async def test_sse_rejects_cursor_outside_authorized_investigation():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from fastapi import HTTPException
    from app.api.v1.investigations import stream_investigation_events
    rows = []
    for value in (SimpleNamespace(workspace_id=uuid.uuid4()), object(), None):
        result = MagicMock()
        result.scalar_one_or_none.return_value = value
        rows.append(result)
    db = AsyncMock()
    db.execute.side_effect = rows
    with pytest.raises(HTTPException) as error:
        await stream_investigation_events(uuid.uuid4(), SimpleNamespace(headers={"last-event-id": str(uuid.uuid4())}), SimpleNamespace(id=uuid.uuid4()), db)
    assert error.value.status_code == 404
