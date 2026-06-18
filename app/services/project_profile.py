"""Helpers de perfil de espacio (reemplazo de project.tipo en runtime)."""
from __future__ import annotations

import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.domain.packs.catalog import get_pack_manifest
from app.domain.project_templates import project_tipo_for_project
from app.models.entities import Project, ProjectMember, ProjectRole

BLOCKING_WITH_CLIENT = frozenset(
    {"pendiente_aprobacion_pm", "esperando_cliente", "respuesta_cliente"}
)
BLOCKING_INTERNAL = frozenset({"esperando_pm"})


def has_role_slug(db: Session, project_id: uuid.UUID, role_slug: str) -> bool:
    """True si el proyecto tiene el rol sistema definido (aunque sin miembros)."""
    role = db.scalar(
        select(ProjectRole.id).where(
            ProjectRole.project_id == project_id,
            ProjectRole.slug == role_slug,
        )
    )
    return role is not None


def has_member_with_role_slug(
    db: Session, project_id: uuid.UUID, role_slug: str
) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.role_id == ProjectRole.id,
                    ProjectRole.project_id == project_id,
                    ProjectRole.slug == role_slug,
                )
            )
        )
    )


def list_project_role_slugs(db: Session, project_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(ProjectRole.slug)
            .where(ProjectRole.project_id == project_id)
            .order_by(ProjectRole.orden.asc())
        )
    )


def pack_supports(db: Session, project: Project, trait: str) -> bool:
    manifest = get_pack_manifest(project.pack_slug or "software")
    if manifest is None:
        return False
    traits = manifest.traits or {}
    return bool(traits.get(trait))


def supports_external_stakeholder(db: Session, project: Project) -> bool:
    return has_role_slug(db, project.id, "cliente")


def supports_reports(db: Session, project: Project) -> bool:
    if not pack_supports(db, project, "supports_reports"):
        return False
    return supports_external_stakeholder(db, project)


def blocking_query_states(db: Session, project: Project) -> frozenset[str]:
    if supports_external_stakeholder(db, project):
        blocking = set(BLOCKING_WITH_CLIENT)
        if project_tipo_for_project(project) == "freestyle":
            blocking |= BLOCKING_INTERNAL
        return frozenset(blocking)
    return BLOCKING_INTERNAL


def active_query_target(db: Session, project: Project) -> str:
    if supports_external_stakeholder(db, project):
        return "esperando_cliente"
    return "esperando_pm"


def legacy_tipo_for_project(project: Project) -> str:
    """Alias de compatibilidad; preferir project_tipo_for_project."""
    return project_tipo_for_project(project)
