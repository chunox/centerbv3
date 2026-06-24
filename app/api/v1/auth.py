import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.entities import PasswordResetToken, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionResponse,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    register_user,
)

router = APIRouter()

REFRESH_COOKIE = "refresh_token"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 días en segundos


def _set_refresh_cookie(response: Response, token: str) -> None:
    # secure=True solo en producción — en HTTP local el browser descarta cookies seguras
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=not settings.is_dev,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
    )


@router.post("/register", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    user = register_user(db, body.nombre, body.email, body.password)
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)
    return SessionResponse(user=UserResponse.model_validate(user), access_token=access_token)


@router.post("/login", response_model=SessionResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.email, body.password)
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)
    return SessionResponse(user=UserResponse.model_validate(user), access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
):
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No hay refresh token")

    user_id = decode_token(refresh_token, expected_type="refresh")
    user = get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no válido")

    new_access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(access_token=new_access)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(REFRESH_COOKIE)
    return {"message": "Sesión cerrada"}


@router.get("/session", response_model=SessionResponse)
def session(
    current_user: User = Depends(get_current_user),
    response: Response = None,
):
    """Devuelve el usuario actual. Útil para restaurar sesión en el frontend al recargar."""
    access_token = create_access_token(current_user.id)
    return SessionResponse(user=UserResponse.model_validate(current_user), access_token=access_token)


logger = logging.getLogger(__name__)

RESET_TOKEN_TTL_HOURS = 1


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Genera un token de reset de contraseña y lo "envía" (en dev: solo lo loguea).
    No revela si el email existe o no.
    """
    user = get_user_by_email(db, body.email)
    if not user or not user.is_active:
        return  # Silencioso — no revelar si el email existe

    # Invalidar tokens anteriores del usuario
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).delete()

    token_value = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token_value,
        expires_at=expires,
    )
    db.add(reset_token)
    db.commit()

    # En producción: enviar email con link /reset-password?token=<token_value>
    # En desarrollo: loguear el token
    reset_link = f"http://localhost:5173/reset-password?token={token_value}"
    logger.info("PASSWORD RESET LINK (dev only): %s", reset_link)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Valida el token y actualiza el password_hash del usuario."""
    now = datetime.now(timezone.utc)
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == body.token,
        PasswordResetToken.used_at.is_(None),
    ).first()

    if not reset_token:
        raise HTTPException(status_code=400, detail="Token inválido o ya utilizado")

    # Compatibilidad: expires_at puede ser timezone-naive
    expires = reset_token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=400, detail="Token expirado")

    user = get_user_by_id(db, reset_token.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario no válido")

    user.password_hash = hash_password(body.new_password)
    reset_token.used_at = now
    db.commit()
