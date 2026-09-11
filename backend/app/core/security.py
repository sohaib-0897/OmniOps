from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
import hashlib
import secrets
import uuid
import jwt
import bcrypt
from app.core.config import settings

MAX_PASSWORD_BYTES = 72

def _password_bytes(password: str) -> bytes:
    value = password.encode("utf-8")
    if len(value) > MAX_PASSWORD_BYTES:
        raise ValueError("Password exceeds the 72-byte bcrypt safety limit.")
    return value

def get_password_hash(password: str) -> str:
    """Hash password securely using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(_password_bytes(password), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return bcrypt.checkpw(
            _password_bytes(plain_password),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def create_access_token(subject: Union[str, Any], session_id: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate signed JWT access token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "iat": datetime.now(timezone.utc)
        ,"jti": str(uuid.uuid4()), "sid": str(session_id), "typ": "access"
    }
    encoded_jwt = jwt.encode(to_encode, settings.get_secret_key(), algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate JWT access token."""
    try:
        payload = jwt.decode(token, settings.get_secret_key(), algorithms=[settings.ALGORITHM], options={"require": ["sub", "exp", "iat", "jti", "sid", "typ"]})
        return payload if payload.get("typ") == "access" else None
    except (jwt.PyJWTError, Exception):
        return None

def new_refresh_secret() -> str:
    return secrets.token_urlsafe(48)

def hash_refresh_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("ascii")).hexdigest()

def encode_refresh_token(token_id: uuid.UUID, secret: str) -> str:
    return f"{token_id}.{secret}"

def parse_refresh_token(value: str) -> tuple[uuid.UUID, str] | None:
    try:
        token_id, secret = value.split(".", 1)
        return uuid.UUID(token_id), secret
    except (ValueError, AttributeError):
        return None
