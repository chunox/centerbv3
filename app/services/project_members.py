"""Gestión de miembros del proyecto (§4.3)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectMember
from app.schemas.projects import ProjectMemberCreate, ProjectMemberUpdate
from app.services.access import (
    assert_member_has_role,
    assert_pm_or_org_admin_of_project,
    assert_project_active,
)
from app.services.audit import record_audit_log


def add_project_member(
    db: Session,
    project: Project,
    payload: ProjectMemberCreate,
) -> ProjectMember:
    assert_project_active(project)
    assert_pm_or_org_admin_of_project(db, project, payload.actor_user_id)

    member = ProjectMember(
        project_id=project.id,
        user_id=payload.user_id,
        rol=payload.rol,
    )
    db.add(member)
    db.flush()
    record_audit_log(
        db,
        project_id=project.id,
        user_id=payload.actor_user_id,
        entidad_tipo="project",
        entidad_id=member.id,
        accion="created",
        campo="member",
        valor_nuevo=f"{payload.user_id}:{payload.rol}",
    )
    return member


def update_project_member_role(
    db: Session,
    project: Project,
    member: ProjectMember,
    payload: ProjectMemberUpdate,
) -> None:
    assert_project_active(project)
    assert_member_has_role(db, project.id, payload.actor_user_id, "pm")

    if member.rol == payload.rol:
        return

    ya_tiene_rol = db.scalar(
        select(
            exists().where(
                ProjectMember.project_id == member.project_id,
                ProjectMember.user_id == member.user_id,
                ProjectMember.rol == payload.rol,
                ProjectMember.id != member.id,
            )
        )
    )
    if ya_tiene_rol:
        raise HTTPException(
            status_code=409,
            detail="Ese usuario ya tiene ese rol en el proyecto",
        )

    anterior = member.rol
    member.rol = payload.rol
    record_audit_log(
        db,
        project_id=project.id,
        user_id=payload.actor_user_id,
        entidad_tipo="project",
        entidad_id=member.id,
        accion="updated",
        campo="rol",
        valor_anterior=anterior,
        valor_nuevo=payload.rol,
    )


def remove_project_member(
    db: Session,
    project: Project,
    member: ProjectMember,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_member_has_role(db, project.id, actor_user_id, "pm")

    if member.rol == "pm":
        pm_count = db.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .where(
                ProjectMember.project_id == member.project_id,
                ProjectMember.rol == "pm",
            )
        )
        if pm_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="No se puede quitar el único PM del proyecto",
            )

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="project",
        entidad_id=member.id,
        accion="deleted",
        campo="member",
        valor_anterior=f"{member.user_id}:{member.rol}",
    )
    db.delete(member)
