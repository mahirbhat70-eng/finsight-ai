"""Security (Phase 7): bcrypt users, JWT access tokens (30 min), API keys
with prefix lookup. `auth_enabled` is off in dev (APP_ENV=dev) so the demo
runs without accounts; prod requires it.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import get_db
from app.models import ApiKey, User

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        pwd_bytes = password.encode("utf-8")[:72]
        return bcrypt.checkpw(pwd_bytes, password_hash.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user: User, minutes: int | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id), "role": user.role, "email": user.email,
        "iat": now, "exp": now + timedelta(
            minutes=minutes or settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "invalid or expired token") from exc


# --- API keys: fs_<prefix>_<secret>; store hash, look up by prefix ---------

def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key, key_hash, prefix)."""
    prefix = uuid.uuid4().hex[:8]
    secret = uuid.uuid4().hex
    full_key = f"fs_{prefix}_{secret}"
    return full_key, bcrypt.hash(full_key), prefix


async def _user_from_api_key(db: AsyncSession, raw_key: str) -> User | None:
    parts = raw_key.split("_")
    if len(parts) != 3:
        return None
    prefix = parts[1]
    keys = (await db.execute(
        select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.revoked.is_(False))
    )).scalars().all()
    for key in keys:
        if bcrypt.verify(raw_key, key.key_hash):
            return await db.get(User, key.user_id)
    return None


async def get_current_user(request: Request,
                           db: Annotated[AsyncSession, Depends(get_db)]
                           ) -> User:
    settings = get_settings()
    if settings.app_env == "dev" and not settings.jwt_secret.startswith("prod"):
        # dev demo mode: anonymous analyst (flip APP_ENV=staging|prod to enforce)
        user = (await db.execute(select(User).limit(1))).scalars().first()
        if user is None:
            user = User(email="dev@finsight.local",
                        password_hash=hash_password("dev"), role="analyst")
            db.add(user)
            await db.commit()
        return user

    auth = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")
    if auth.startswith("Bearer "):
        payload = decode_token(auth.removeprefix("Bearer "))
        user = await db.get(User, uuid.UUID(payload["sub"]))
        if user is None:
            raise HTTPException(401, "user not found")
        return user
    if api_key:
        user = await _user_from_api_key(db, api_key)
        if user is not None:
            return user
    raise HTTPException(401, "authentication required (Bearer token or X-API-Key)")


def require_role(role: str):
    async def _guard(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role != role and user.role != "admin":
            raise HTTPException(403, f"requires {role} role")
        return user
    return _guard
