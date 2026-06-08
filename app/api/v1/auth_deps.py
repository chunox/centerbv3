"""
Dependencias FastAPI para auth JWT.

AuthContext = usuario autenticado + org_id embebida en el token.
get_optional_auth: Bearer opcional (endpoints que también aceptan demo_mode + user_id).
get_current_auth: exige token válido.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.entities import Organization, User
from app.services.auth_tokens import decode_access_token
from app.services.organizations import get_org_member, require_org_member

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user: User
    organization_id: UUID | None = None


def get_optional_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AuthContext | None:
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    user_id = UUID(payload["sub"])
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    org_raw = payload.get("org_id")
    org_id = UUID(org_raw) if org_raw else None
    if org_id is not None:
        require_org_member(db, org_id, user.id)
    return AuthContext(user=user, organization_id=org_id)


def get_current_auth(
    auth: AuthContext | None = Depends(get_optional_auth),
) -> AuthContext:
    if auth is None:
        if settings.demo_mode:
            raise HTTPException(
                status_code=401,
                detail="Se requiere Authorization Bearer (o demo_mode con query params)",
            )
        raise HTTPException(status_code=401, detail="No autenticado")
    return auth


def get_current_user(auth: AuthContext = Depends(get_current_auth)) -> User:
    return auth.user


def get_current_org_id(auth: AuthContext = Depends(get_current_auth)) -> UUID:
    if auth.organization_id is None:
        raise HTTPException(status_code=400, detail="No hay organización activa en la sesión")
    return auth.organization_id


def get_organization_or_404(organization_id: UUID, db: Session = Depends(get_db)) -> Organization:
    org = db.get(Organization, organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organización no encontrada")
    return org
