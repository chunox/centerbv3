"""JWT HS256: claims sub (user) y org_id (organización activa en la sesión)."""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import jwt
from fastapi import HTTPException

from app.config import settings


def create_access_token(
    *,
    user_id: UUID,
    organization_id: UUID | None = None,
    expires_minutes: int | None = None,
) -> str:
    ttl = expires_minutes or settings.jwt_expire_minutes
    payload = {
        "sub": str(user_id),
        "org_id": str(organization_id) if organization_id else None,
        "exp": datetime.utcnow() + timedelta(minutes=ttl),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Token inválido o expirado") from exc
