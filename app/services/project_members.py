"""Gestión de miembros del proyecto (§4.3)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.domain.capabilities import PROJECT_MEMBERS_MANAGE
from app.models.entities import Project, ProjectMember, ProjectRole
from app.schemas.projects import ProjectMemberCreate, ProjectMemberRead, ProjectMemberUpdate
from app.services.access import (
    assert_member_has_role,
    assert_pm_or_org_admin_of_project,
    assert_project_active,
)
from app.services.audit import record_audit_log
from app.services.workflow.authorize import assert_capability


def _resolve_role_id(
    db: Session, project_id: uuid.UUID, *, role_id: uuid.UUID | None, rol: str | None
) -> uuid.UUID:
    if role_id is not None:
        role = db.get(ProjectRole, role_id)
        if not role or role.project_id != project_id:
            raise HTTPException(status_code=404, detail="Rol no encontrado")
        return role_id
    if rol is not None:
        role = db.scalar(
            select(ProjectRole).where(
                ProjectRole.project_id == project_id, ProjectRole.slug == rol
            )
        )
        if not role:
            raise HTTPException(status_code=404, detail=f"Rol '{rol}' no encontrado")
        return role.id
    raise HTTPException(status_code=422, detail="Se requiere role_id o rol")


def member_to_read(member: ProjectMember) -> ProjectMemberRead:
    role = member.role
    legacy_rol = role.slug if role and role.slug in ("pm", "dev", "qa", "cliente") else None
    return ProjectMemberRead(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role_id=member.role_id,
        role_slug=role.slug if role else "",
        role_nombre=role.nombre if role else "",
        rol=legacy_rol,  # type: ignore[arg-type]
        joined_at=member.joined_at,
    )


def add_project_member(
    db: Session,
    project: Project,
    payload: ProjectMemberCreate,
    *,
    actor_user_id: uuid.UUID,
) -> ProjectMember:
    assert_project_active(project)
    assert_pm_or_org_admin_of_project(db, project, actor_user_id)

    role_id = _resolve_role_id(
        db, project.id, role_id=payload.role_id, rol=payload.rol
    )
    ya_tiene = db.scalar(
        select(
            exists().where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == payload.user_id,
                ProjectMember.role_id == role_id,
            )
        )
    )
    if ya_tiene:
        raise HTTPException(status_code=409, detail="El usuario ya tiene ese rol")

    member = ProjectMember(
        project_id=project.id,
        user_id=payload.user_id,
        role_id=role_id,
    )
    db.add(member)
    db.flush()
    role = db.get(ProjectRole, role_id)
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="project",
        entidad_id=member.id,
        accion="created",
        campo="member",
        valor_nuevo=f"{payload.user_id}:{role.slug if role else role_id}",
    )
    return member


def update_project_member_role(
    db: Session,
    project: Project,
    member: ProjectMember,
    payload: ProjectMemberUpdate,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_capability(db, project.id, actor_user_id, PROJECT_MEMBERS_MANAGE)

    new_role_id = _resolve_role_id(
        db, project.id, role_id=payload.role_id, rol=payload.rol
    )
    if member.role_id == new_role_id:
        return

    ya_tiene_rol = db.scalar(
        select(
            exists().where(
                ProjectMember.project_id == member.project_id,
                ProjectMember.user_id == member.user_id,
                ProjectMember.role_id == new_role_id,
                ProjectMember.id != member.id,
            )
        )
    )
    if ya_tiene_rol:
        raise HTTPException(
            status_code=409,
            detail="Ese usuario ya tiene ese rol en el proyecto",
        )

    old_role = db.get(ProjectRole, member.role_id)
    new_role = db.get(ProjectRole, new_role_id)
    anterior = old_role.slug if old_role else str(member.role_id)
    member.role_id = new_role_id
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="project",
        entidad_id=member.id,
        accion="updated",
        campo="rol",
        valor_anterior=anterior,
        valor_nuevo=new_role.slug if new_role else str(new_role_id),
    )


def remove_project_member(
    db: Session,
    project: Project,
    member: ProjectMember,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_capability(db, project.id, actor_user_id, PROJECT_MEMBERS_MANAGE)

    role = db.get(ProjectRole, member.role_id)
    if role and role.slug == "pm":
        pm_count = db.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .join(ProjectRole, ProjectRole.id == ProjectMember.role_id)
            .where(
                ProjectMember.project_id == member.project_id,
                ProjectRole.slug == "pm",
            )
        )
        if pm_count is not None and pm_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="No se puede quitar el único PM del proyecto",
            )

    role_slug = role.slug if role else str(member.role_id)
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="project",
        entidad_id=member.id,
        accion="deleted",
        campo="member",
        valor_anterior=f"{member.user_id}:{role_slug}",
    )
    db.delete(member)
