import hashlib, hmac
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import client_ip, enforce_rate_limit
from app.core.security import create_access_token, encode_refresh_token, get_password_hash, hash_refresh_secret, new_refresh_secret, parse_refresh_token, verify_password
from app.models.user import RefreshToken, User, UserSession, Workspace, WorkspaceMembership, WorkspaceRole
from app.schemas.auth import AuthSessionResponse, TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse
from app.schemas.common import ResponseEnvelope

router = APIRouter(prefix="/auth", tags=["Authentication"])

def _set_cookie(response: Response, value: str) -> None:
    response.set_cookie(settings.REFRESH_COOKIE_NAME, value, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, httponly=True,
        secure=settings.COOKIE_SECURE, samesite=settings.COOKIE_SAMESITE.lower(), path=f"{settings.API_V1_PREFIX}/auth")

def _clear_cookie(response: Response) -> None:
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=f"{settings.API_V1_PREFIX}/auth", secure=settings.COOKIE_SECURE,
        httponly=True, samesite=settings.COOKIE_SAMESITE.lower())

def _validate_browser_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in settings.CORS_ORIGINS:
        raise HTTPException(status_code=403, detail="Browser origin is not allowed.")

async def _new_session(db: AsyncSession, user: User, request: Request, response: Response) -> AuthSessionResponse:
    now, expiry = datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ua = request.headers.get("user-agent", "")[:1024]
    session = UserSession(user_id=user.id, expires_at=expiry, last_used_at=now, user_agent_hash=hashlib.sha256(ua.encode()).hexdigest() if ua else None)
    db.add(session); await db.flush()
    secret = new_refresh_secret(); refresh = RefreshToken(session_id=session.id, token_hash=hash_refresh_secret(secret), expires_at=expiry)
    db.add(refresh); await db.flush(); _set_cookie(response, encode_refresh_token(refresh.id, secret))
    return AuthSessionResponse(user=UserResponse.model_validate(user), token=TokenResponse(access_token=create_access_token(user.id, session.id), expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60))

@router.post("/register", response_model=ResponseEnvelope[AuthSessionResponse])
async def register_user(req: UserRegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(db, key=f"register:ip:{client_ip(request)}", limit=settings.RATE_LIMIT_REGISTER_PER_HOUR, window_seconds=3600)
    email = req.email.lower().strip()
    if (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Unable to create account with those details.")
    user = User(email=email, hashed_password=get_password_hash(req.password), full_name=req.full_name.strip()); db.add(user); await db.flush()
    workspace = Workspace(name=f"{req.full_name.split()[0]}'s Workspace", description="Default business intelligence workspace.", created_by=user.id); db.add(workspace); await db.flush()
    db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER.value))
    result = await _new_session(db, user, request, response); await db.commit(); return ResponseEnvelope.ok(result)

@router.post("/login", response_model=ResponseEnvelope[AuthSessionResponse])
async def login_user(req: UserLoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    ip, email = client_ip(request), req.email.lower().strip()
    await enforce_rate_limit(db, key=f"login:ip:{ip}", limit=settings.RATE_LIMIT_LOGIN_PER_5_MINUTES, window_seconds=300)
    await enforce_rate_limit(db, key=f"login:account:{hashlib.sha256(email.encode()).hexdigest()}", limit=settings.RATE_LIMIT_LOGIN_PER_5_MINUTES, window_seconds=300)
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password): raise HTTPException(status_code=401, detail="Invalid email or password.")
    result = await _new_session(db, user, request, response); await db.commit(); return ResponseEnvelope.ok(result)

@router.post("/refresh", response_model=ResponseEnvelope[AuthSessionResponse])
async def refresh_session(request: Request, response: Response, refresh_value: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME), db: AsyncSession = Depends(get_db)):
    _validate_browser_origin(request)
    await enforce_rate_limit(db, key=f"refresh:ip:{client_ip(request)}", limit=settings.RATE_LIMIT_REFRESH_PER_5_MINUTES, window_seconds=300)
    parsed = parse_refresh_token(refresh_value or "")
    if not parsed: _clear_cookie(response); raise HTTPException(status_code=401, detail="Refresh session is invalid or expired.")
    token_id, secret = parsed
    token = (await db.execute(select(RefreshToken).where(RefreshToken.id == token_id).with_for_update())).scalar_one_or_none(); now = datetime.now(timezone.utc)
    if not token or not hmac.compare_digest(token.token_hash, hash_refresh_secret(secret)): _clear_cookie(response); raise HTTPException(status_code=401, detail="Refresh session is invalid or expired.")
    session = (await db.execute(select(UserSession).where(UserSession.id == token.session_id).with_for_update())).scalar_one()
    def expired(value):
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value) <= now
    if token.consumed_at or token.revoked_at:
        session.revoked_at = now; await db.execute(update(RefreshToken).where(RefreshToken.session_id == session.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now)); await db.commit(); _clear_cookie(response)
        from app.core.observability import logger
        import json
        logger.warning(json.dumps({"event_type": "auth.refresh_replay", "session_id": str(session.id), "request_id": getattr(request.state, "request_id", None)}))
        raise HTTPException(status_code=401, detail="Refresh token reuse detected; session revoked.")
    if session.revoked_at or expired(session.expires_at) or expired(token.expires_at): _clear_cookie(response); raise HTTPException(status_code=401, detail="Refresh session is invalid or expired.")
    user = (await db.execute(select(User).where(User.id == session.user_id))).scalar_one(); token.consumed_at, session.last_used_at = now, now; session.rotation_counter += 1
    replacement_secret = new_refresh_secret(); replacement = RefreshToken(session_id=session.id, token_hash=hash_refresh_secret(replacement_secret), expires_at=session.expires_at); db.add(replacement); await db.flush(); token.replaced_by_id = replacement.id
    _set_cookie(response, encode_refresh_token(replacement.id, replacement_secret)); access = create_access_token(user.id, session.id); await db.commit()
    return ResponseEnvelope.ok(AuthSessionResponse(user=UserResponse.model_validate(user), token=TokenResponse(access_token=access, expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)))

@router.post("/logout", response_model=ResponseEnvelope[dict])
async def logout(request: Request, response: Response, refresh_value: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME), db: AsyncSession = Depends(get_db)):
    _validate_browser_origin(request)
    parsed = parse_refresh_token(refresh_value or "")
    if parsed:
        token = (await db.execute(select(RefreshToken).where(RefreshToken.id == parsed[0]))).scalar_one_or_none()
        if token:
            now = datetime.now(timezone.utc); await db.execute(update(UserSession).where(UserSession.id == token.session_id).values(revoked_at=now)); await db.execute(update(RefreshToken).where(RefreshToken.session_id == token.session_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now)); await db.commit()
    _clear_cookie(response); return ResponseEnvelope.ok({"logged_out": True})

@router.post("/logout-all", response_model=ResponseEnvelope[dict])
async def logout_all(response: Response, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(UserSession).where(UserSession.user_id == current_user.id, UserSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc))); await db.commit(); _clear_cookie(response)
    return ResponseEnvelope.ok({"logged_out_all": True})

@router.get("/me", response_model=ResponseEnvelope[UserResponse])
async def get_current_user_profile(current_user: User = Depends(get_current_user)): return ResponseEnvelope.ok(UserResponse.model_validate(current_user))
