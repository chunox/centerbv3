"""Recuperación de contraseña por token de un solo uso."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PasswordResetToken, User
from app.security import hash_password

logger = logging.getLogger(__name__)

RESET_MESSAGE = (
    "Si el email está registrado, recibirás instrucciones para restablecer la contraseña."
)


def request_password_reset(db: Session, email: str, *, expires_hours: int = 24) -> str:
    """Crea token si el usuario existe. En dev el token se loguea (sin email real)."""
    normalized = email.lower().strip()
    user = db.scalar(select(User).where(User.email == normalized))
    if user is None:
        return RESET_MESSAGE

    token_value = secrets.token_urlsafe(32)
    row = PasswordResetToken(
        user_id=user.id,
        token=token_value,
        expires_at=datetime.utcnow() + timedelta(hours=expires_hours),
    )
    db.add(row)
    db.flush()
    logger.info(
        "password_reset_token user=%s token=%s expires=%s",
        user.email,
        token_value,
        row.expires_at.isoformat(),
    )
    return RESET_MESSAGE


def reset_password_with_token(db: Session, token: str, new_password: str) -> None:
    row = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token == token)
    )
    if not row or row.used_at is not None:
        raise HTTPException(status_code=400, detail="Token inválido o ya utilizado")
    if row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Token expirado")

    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Token inválido o ya utilizado")

    user.password_hash = hash_password(new_password)
    row.used_at = datetime.utcnow()
