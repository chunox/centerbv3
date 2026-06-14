"""Helpers para tests con organizaciones (schema v8)."""

from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.domain.project_profiles import resolve_profile_slug
from app.domain.project_templates import get_template, template_slug_for_legacy_tipo
from app.models.entities import Organization, OrganizationMember, Project, ProjectMember, User
from app.services.packs import seed_project_from_pack
from app.services.project_roles import seed_default_project_access


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
    profile_slug: str | None = None,
    pack_slug: str = "software",
    template_slug: str | None = None,
    estado: str = "activo",
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    add_pm_member: bool = True,
) -> Project:
    if org is None:
        org = create_organization(session, owner_id=pm_id)
    slug = template_slug or template_slug_for_legacy_tipo(tipo)
    tpl = get_template(slug)
    resolved_profile = resolve_profile_slug(
        pack_slug=pack_slug,
        template_profile=tpl.profile_slug,
        legacy_tipo=tipo,
        profile_override=profile_slug,
    )
    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        nombre=nombre,
        profile_slug=resolved_profile,
        template_slug=slug,
        pack_slug=pack_slug,
        estado=estado,
        fecha_inicio=fecha_inicio or date(2026, 1, 1),
        fecha_fin=fecha_fin or date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.flush()
    roles = seed_project_from_pack(session, project, pack_slug, template_slug=slug)
    if add_pm_member:
        creator_role = get_template(slug).creator_role
        session.add(
            ProjectMember(
                project_id=project.id,
                user_id=pm_id,
                role_id=roles[creator_role].id,
            )
        )
        session.flush()
    return project


def _ensure_project_roles(session: Session, project: Project) -> None:
    from sqlalchemy import select

    from app.models.entities import ProjectRole

    exists = session.scalar(
        select(ProjectRole.id)
        .where(ProjectRole.project_id == project.id)
        .limit(1)
    )
    if not exists:
        seed_default_project_access(session, project)


def add_member_with_slug(
    session: Session,
    project: Project,
    user_id: uuid.UUID,
    role_slug: str,
) -> ProjectMember:
    from sqlalchemy import select

    from app.models.entities import ProjectRole

    _ensure_project_roles(session, project)
    role = session.scalar(
        select(ProjectRole).where(
            ProjectRole.project_id == project.id, ProjectRole.slug == role_slug
        )
    )
    if not role:
        raise ValueError(f"Rol '{role_slug}' no encontrado en el proyecto")
    member = ProjectMember(
        project_id=project.id, user_id=user_id, role_id=role.id
    )
    session.add(member)
    session.flush()
    return member


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
