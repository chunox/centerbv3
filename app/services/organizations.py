"""
Lógica de negocio — organizaciones y aislamiento multi-tenant.

Jerarquía: Organization → Project → Milestone → Feature.

Reglas clave:
- ORG_ADMIN_ROLES (owner/admin) ven todos los proyectos de la org
- Miembros org no-admin solo ven proyectos donde son project_member
- list_guest_projects: project_member en org ajena (cliente externo)
- user_has_project_access: admin org O project_member
"""
from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Organization,
    OrganizationInvite,
    OrganizationMember,
    Project,
    ProjectMember,
    User,
)
from app.schemas.organizations import OrganizationCreate, OrganizationUpdate

ORG_ADMIN_ROLES = frozenset({"owner", "admin"})


def slugify(nombre: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", nombre.lower()).strip("-")
    return base or f"org-{uuid.uuid4().hex[:8]}"


def unique_slug(db: Session, base: str) -> str:
    slug = base
    n = 0
    while db.scalar(select(Organization.id).where(Organization.slug == slug)):
        n += 1
        slug = f"{base}-{n}"
    return slug


def get_org_member(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID
) -> OrganizationMember | None:
    return db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )


def require_org_member(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID
) -> OrganizationMember:
    member = get_org_member(db, organization_id, user_id)
    if not member:
        raise HTTPException(status_code=403, detail="No eres miembro de la organización")
    return member


def require_org_admin(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID
) -> OrganizationMember:
    member = require_org_member(db, organization_id, user_id)
    if member.rol not in ORG_ADMIN_ROLES:
        raise HTTPException(
            status_code=403, detail="Se requiere rol owner o admin en la organización"
        )
    return member


def user_has_project_access(
    db: Session,
    project: Project,
    user_id: uuid.UUID,
) -> bool:
    org_member = get_org_member(db, project.organization_id, user_id)
    if org_member and org_member.rol in ORG_ADMIN_ROLES:
        return True
    pm = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user_id,
        )
    )
    return pm is not None


def create_organization(
    db: Session, user_id: uuid.UUID, payload: OrganizationCreate
) -> Organization:
    base_slug = slugify(payload.slug or payload.nombre)
    slug = unique_slug(db, base_slug)
    org = Organization(nombre=payload.nombre, slug=slug, estado="activa")
    db.add(org)
    db.flush()
    db.add(
        OrganizationMember(
            organization_id=org.id,
            user_id=user_id,
            rol="owner",
        )
    )
    db.flush()
    return org


def update_organization(
    db: Session, org: Organization, payload: OrganizationUpdate
) -> Organization:
    if payload.nombre is not None:
        org.nombre = payload.nombre
    if payload.slug is not None:
        candidate = slugify(payload.slug)
        existing = db.scalar(
            select(Organization.id).where(
                Organization.slug == candidate,
                Organization.id != org.id,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail="El slug ya está en uso")
        org.slug = candidate
    return org


def list_user_organizations(db: Session, user_id: uuid.UUID) -> list[Organization]:
    stmt = (
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user_id)
        .order_by(Organization.nombre)
    )
    return list(db.scalars(stmt))


def create_organization_invite(
    db: Session,
    org: Organization,
    *,
    email: str,
    rol: str,
    created_by: uuid.UUID,
    expires_days: int = 7,
) -> OrganizationInvite:
    token = secrets.token_urlsafe(32)
    invite = OrganizationInvite(
        organization_id=org.id,
        email=email.lower().strip(),
        rol=rol,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=expires_days),
        created_by=created_by,
    )
    db.add(invite)
    db.flush()
    return invite


def join_organization_with_token(
    db: Session, user: User, token: str
) -> OrganizationMember:
    invite = db.scalar(
        select(OrganizationInvite).where(OrganizationInvite.token == token)
    )
    if not invite:
        raise HTTPException(status_code=404, detail="Invitación no encontrada")
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Invitación expirada")
    if invite.email.lower() != user.email.lower():
        raise HTTPException(
            status_code=403, detail="La invitación no corresponde a tu email"
        )
    existing = get_org_member(db, invite.organization_id, user.id)
    if existing:
        return existing
    member = OrganizationMember(
        organization_id=invite.organization_id,
        user_id=user.id,
        rol=invite.rol,
    )
    db.add(member)
    db.delete(invite)
    db.flush()
    return member


def list_org_projects(
    db: Session,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[Project]:
    org_member = get_org_member(db, organization_id, user_id)
    if not org_member:
        raise HTTPException(status_code=403, detail="No eres miembro de la organización")

    # Admins/owners: visibilidad total de la org sin necesitar project_member.
    if org_member.rol in ORG_ADMIN_ROLES:
        stmt = (
            select(Project)
            .where(Project.organization_id == organization_id)
            .order_by(Project.created_at.desc())
        )
        return list(db.scalars(stmt))

    stmt = (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            Project.organization_id == organization_id,
            ProjectMember.user_id == user_id,
        )
        .distinct()
        .order_by(Project.created_at.desc())
    )
    return list(db.scalars(stmt))


def list_guest_projects(db: Session, user_id: uuid.UUID) -> list[Project]:
    """Proyectos donde el usuario es project_member pero no organization_member."""
    org_ids_subq = (
        select(OrganizationMember.organization_id).where(
            OrganizationMember.user_id == user_id
        )
    )
    stmt = (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user_id,
            Project.organization_id.not_in(org_ids_subq),
        )
        .distinct()
        .order_by(Project.created_at.desc())
    )
    return list(db.scalars(stmt))
