"""Auth endpoints (Phase 7): login (JWT) + API key issuance."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    generate_api_key,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models import ApiKey, User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
async def login(payload: LoginIn,
                db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    user = (await db.execute(
        select(User).where(User.email == payload.email))).scalars().first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    token = create_access_token(user)
    return {"access_token": token, "token_type": "bearer", "role": user.role}


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    role: str = "analyst"


@router.post("/register", status_code=201)
async def register(payload: RegisterIn,
                   db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    existing = (await db.execute(
        select(User).where(User.email == payload.email))).scalars().first()
    if existing is not None:
        raise HTTPException(409, "email already registered")
    user = User(email=payload.email, password_hash=hash_password(payload.password),
                role=payload.role)
    db.add(user)
    await db.commit()
    return {"user_id": str(user.id), "email": user.email, "role": user.role}


@router.post("/api-keys", status_code=201)
async def issue_api_key(db: Annotated[AsyncSession, Depends(get_db)],
                        user: Annotated[User, Depends(get_current_user)]) -> dict:
    full_key, key_hash, prefix = generate_api_key()
    db.add(ApiKey(user_id=user.id, key_hash=key_hash, prefix=prefix))
    await db.commit()
    # the full key is shown exactly once
    return {"api_key": full_key,
            "prefix": prefix,
            "note": "store it now — only the hash is persisted"}
