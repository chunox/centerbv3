"""
Autenticación JWT y estado de onboarding.

El token incluye sub (user_id) y org_id (organización activa, opcional).
Registro no crea org: el usuario pasa por onboarding o invitación.

onboarding-status.needs_onboarding = sin org membership Y sin proyectos guest.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import AuthContext, get_current_auth, get_optional_auth
from app.database import get_db
from app.models.entities import User
from app.schemas.auth import (
    AuthLogin,
    AuthRegister,
    AuthSwitchOrganization,
    AuthTokenResponse,
)
from app.schemas.organizations import OrganizationRead
from app.schemas.users import UserRead
from app.security import hash_password, verify_password
from app.services.auth_tokens import create_access_token
from app.services.organizations import (
    list_guest_projects,
    list_user_organizations,
    require_org_member,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(
    db: Session,
    user: User,
    organization_id: UUID | None = None,
) -> AuthTokenResponse:
    """Arma JWT + metadatos de orgs; si hay una sola org, la fija como activa."""
    orgs = list_user_organizations(db, user.id)
    active_org = organization_id
    if active_org is None and len(orgs) == 1:
        active_org = orgs[0].id
    token = create_access_token(user_id=user.id, organization_id=active_org)
    return AuthTokenResponse(
        access_token=token,
        user=UserRead.model_validate(user),
        organization_id=active_org,
        organizations=[OrganizationRead.model_validate(o) for o in orgs],
    )


@router.post("/register", response_model=AuthTokenResponse, status_code=201)
def register(payload: AuthRegister, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="El email ya está registrado")
    user = User(
        nombre=payload.nombre,
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(db, user, organization_id=None)


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: AuthLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    return _token_response(db, user)


@router.post("/switch-organization", response_model=AuthTokenResponse)
def switch_organization(
    payload: AuthSwitchOrganization,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    require_org_member(db, payload.organization_id, auth.user.id)
    db.commit()
    return _token_response(db, auth.user, organization_id=payload.organization_id)


@router.get("/session", response_model=AuthTokenResponse)
def get_session(
    auth: AuthContext | None = Depends(get_optional_auth),
    db: Session = Depends(get_db),
):
    if auth is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    return _token_response(db, auth.user, organization_id=auth.organization_id)


@router.get("/onboarding-status")
def onboarding_status(
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    orgs = list_user_organizations(db, auth.user.id)
    guests = list_guest_projects(db, auth.user.id)
    return {
        "has_organizations": len(orgs) > 0,
        "has_guest_projects": len(guests) > 0,
        "needs_onboarding": len(orgs) == 0 and len(guests) == 0,
    }
