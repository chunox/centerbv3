"""Helpers para tests con organizaciones (schema v8)."""

from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.models.entities import Organization, OrganizationMember, Project, ProjectMember, User


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or f"org-{uuid.uuid4().hex[:8]}"


def create_organization(
    session: Session,
    *,
    nombre: str = "Test Org",
    slug: str | None = None,
    owner_id: uuid.UUID | None = None,
    owner_rol: str = "owner",
) -> Organization:
    base_slug = slug or slugify(nombre)
    candidate = f"{base_slug}-{uuid.uuid4().hex[:8]}"
    org = Organization(
        id=uuid.uuid4(),
        nombre=nombre,
        slug=candidate,
        estado="activa",
    )
    session.add(org)
    session.flush()
    if owner_id is not None:
        session.add(
            OrganizationMember(
                organization_id=org.id,
                user_id=owner_id,
                rol=owner_rol,
            )
        )
        session.flush()
    return org


def create_project_for_org(
    session: Session,
    pm_id: uuid.UUID,
    org: Organization | None = None,
    *,
    nombre: str = "P",
    tipo: str = "interno",
    estado: str = "activo",
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    add_pm_member: bool = True,
) -> Project:
    if org is None:
        org = create_organization(session, owner_id=pm_id)
    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        nombre=nombre,
        tipo=tipo,
        estado=estado,
        fecha_inicio=fecha_inicio or date(2026, 1, 1),
        fecha_fin=fecha_fin or date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.flush()
    if add_pm_member:
        session.add(
            ProjectMember(project_id=project.id, user_id=pm_id, rol="pm")
        )
        session.flush()
    return project


def create_user(
    session: Session,
    *,
    email: str | None = None,
    nombre: str = "User",
) -> User:
    user = User(
        id=uuid.uuid4(),
        nombre=nombre,
        email=email or f"{uuid.uuid4().hex[:8]}@test.local",
        password_hash="x",
    )
    session.add(user)
    session.flush()
    return user
