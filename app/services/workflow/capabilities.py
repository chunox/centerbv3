"""Resolución de capacidades efectivas por usuario en proyecto."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ProjectMember, ProjectRole, ProjectRoleCapability


def get_user_role_assignments(
    db: Session, project_id: uuid.UUID, user_id: uuid.UUID
) -> list[ProjectRole]:
    stmt = (
        select(ProjectRole)
        .join(ProjectMember, ProjectMember.role_id == ProjectRole.id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        .order_by(ProjectRole.orden.asc())
    )
    return list(db.scalars(stmt))


def get_effective_capabilities(
    db: Session, project_id: uuid.UUID, user_id: uuid.UUID
) -> frozenset[str]:
    role_ids = db.scalars(
        select(ProjectMember.role_id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).all()
    if not role_ids:
        return frozenset()

    caps = db.scalars(
        select(ProjectRoleCapability.capability_key).where(
            ProjectRoleCapability.role_id.in_(role_ids)
        )
    ).all()
    return frozenset(caps)


def user_has_capability(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    capability: str,
) -> bool:
    return capability in get_effective_capabilities(db, project_id, user_id)


def user_ids_with_role_slug(
    db: Session, project_id: uuid.UUID, slug: str
) -> list[uuid.UUID]:
    stmt = (
        select(ProjectMember.user_id)
        .join(ProjectRole, ProjectRole.id == ProjectMember.role_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectRole.slug == slug,
        )
        .distinct()
    )
    return list(db.scalars(stmt))


def users_with_capability(
    db: Session, project_id: uuid.UUID, capability: str
) -> list[uuid.UUID]:
    stmt = (
        select(ProjectMember.user_id)
        .join(ProjectRoleCapability, ProjectRoleCapability.role_id == ProjectMember.role_id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectRoleCapability.capability_key == capability,
        )
        .distinct()
    )
    return list(db.scalars(stmt))
