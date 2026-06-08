"""
API de organizaciones (tenant SaaS).

CRUD de org, miembros e invitaciones. Crear org requiere JWT.
En demo_mode, GET /organizations acepta ?user_id= sin Bearer.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import AuthContext, get_current_auth, get_optional_auth, get_organization_or_404
from app.config import settings
from app.database import get_db
from app.models.entities import OrganizationMember, User
from app.schemas.organizations import (
    OrganizationCreate,
    OrganizationInviteCreate,
    OrganizationInviteRead,
    OrganizationJoin,
    OrganizationMemberCreate,
    OrganizationMemberRead,
    OrganizationRead,
    OrganizationUpdate,
)
from app.services.organizations import (
    create_organization,
    create_organization_invite,
    join_organization_with_token,
    list_user_organizations,
    require_org_admin,
    require_org_member,
    update_organization,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    user_id: UUID | None = Query(default=None, description="Demo sin JWT"),
    auth: AuthContext | None = Depends(get_optional_auth),
    db: Session = Depends(get_db),
):
    if auth is not None:
        return list_user_organizations(db, auth.user.id)
    if settings.demo_mode and user_id is not None:
        return list_user_organizations(db, user_id)
    raise HTTPException(status_code=401, detail="No autenticado")


@router.post("", response_model=OrganizationRead, status_code=201)
def create_organization_endpoint(
    payload: OrganizationCreate,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    org = create_organization(db, auth.user.id, payload)
    db.commit()
    db.refresh(org)
    return org


@router.post("/join", response_model=OrganizationMemberRead)
def join_organization(
    payload: OrganizationJoin,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    member = join_organization_with_token(db, auth.user, payload.token)
    db.commit()
    db.refresh(member)
    return member


@router.get("/{organization_id}", response_model=OrganizationRead)
def get_organization(
    organization_id: UUID,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    require_org_member(db, organization_id, auth.user.id)
    return get_organization_or_404(organization_id, db)


@router.patch("/{organization_id}", response_model=OrganizationRead)
def patch_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    org = get_organization_or_404(organization_id, db)
    require_org_admin(db, organization_id, auth.user.id)
    update_organization(db, org, payload)
    db.commit()
    db.refresh(org)
    return org


@router.get("/{organization_id}/members", response_model=list[OrganizationMemberRead])
def list_organization_members(
    organization_id: UUID,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    require_org_member(db, organization_id, auth.user.id)
    return list(
        db.scalars(
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(OrganizationMember.joined_at)
        )
    )


@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMemberRead,
    status_code=201,
)
def add_organization_member(
    organization_id: UUID,
    payload: OrganizationMemberCreate,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    get_organization_or_404(organization_id, db)
    require_org_admin(db, organization_id, auth.user.id)
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if payload.rol == "owner":
        raise HTTPException(status_code=400, detail="No se puede asignar owner por API")
    existing = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == payload.user_id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="El usuario ya es miembro de la org")
    member = OrganizationMember(
        organization_id=organization_id,
        user_id=payload.user_id,
        rol=payload.rol,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{organization_id}/members/{member_id}", status_code=204)
def remove_organization_member(
    organization_id: UUID,
    member_id: UUID,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    require_org_admin(db, organization_id, auth.user.id)
    member = db.get(OrganizationMember, member_id)
    if not member or member.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")
    if member.rol == "owner":
        raise HTTPException(status_code=400, detail="No se puede quitar al owner")
    db.delete(member)
    db.commit()


@router.post(
    "/{organization_id}/invites",
    response_model=OrganizationInviteRead,
    status_code=201,
)
def create_invite(
    organization_id: UUID,
    payload: OrganizationInviteCreate,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    org = get_organization_or_404(organization_id, db)
    require_org_admin(db, organization_id, auth.user.id)
    invite = create_organization_invite(
        db,
        org,
        email=payload.email,
        rol=payload.rol,
        created_by=auth.user.id,
    )
    db.commit()
    db.refresh(invite)
    return invite
