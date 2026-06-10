"""Transiciones de estado de proyecto (§4.2)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Project
from app.schemas.projects import ProjectUpdate
from app.services.audit import record_audit_log
from app.domain.capabilities import PROJECT_LIFECYCLE_MANAGE, PROJECT_SETTINGS_EDIT
from app.services.feature_queries import assert_project_active
from app.services.workflow.authorize import assert_capability

ProjectEstadoAction = Literal["cerrar", "reabrir", "cancelar"]

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("activo", "cerrar"): "cerrado",
    ("cerrado", "reabrir"): "activo",
    ("activo", "cancelar"): "cancelado",
}


def apply_project_estado_action(
    db: Session,
    project: Project,
    *,
    action: ProjectEstadoAction,
    actor_user_id: uuid.UUID,
) -> None:
    assert_capability(db, project.id, actor_user_id, PROJECT_LIFECYCLE_MANAGE)

    key = (project.estado, action)
    nuevo = _TRANSITIONS.get(key)
    if nuevo is None:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede '{action}' desde estado '{project.estado}'",
        )

    anterior = project.estado
    project.estado = nuevo
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="project",
        entidad_id=project.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior=anterior,
        valor_nuevo=nuevo,
    )


def update_project(
    db: Session,
    project: Project,
    payload: ProjectUpdate,
) -> None:
    assert_project_active(project)
    assert_capability(db, project.id, payload.actor_user_id, PROJECT_SETTINGS_EDIT)

    changes = payload.model_dump(exclude_unset=True, exclude={"actor_user_id"})
    if not changes:
        return

    fecha_inicio = changes.get("fecha_inicio", project.fecha_inicio)
    fecha_fin = changes.get("fecha_fin", project.fecha_fin)
    if fecha_fin < fecha_inicio:
        raise HTTPException(
            status_code=422,
            detail="fecha_fin debe ser mayor o igual que fecha_inicio",
        )

    for field, nuevo in changes.items():
        anterior = getattr(project, field)
        if anterior == nuevo:
            continue
        setattr(project, field, nuevo)
        record_audit_log(
            db,
            project_id=project.id,
            user_id=payload.actor_user_id,
            entidad_tipo="project",
            entidad_id=project.id,
            accion="updated",
            campo=field,
            valor_anterior=str(anterior) if anterior is not None else None,
            valor_nuevo=str(nuevo) if nuevo is not None else None,
        )
