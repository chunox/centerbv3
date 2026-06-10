"""Sync de estado de hito y cancelación en cascada (§4.4, §5.3b)."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Feature, Milestone, Project
from app.schemas.milestones import MilestoneUpdate
from app.services.audit import record_audit_log
from app.domain.capabilities import (
    SCOPE_MILESTONE_CANCEL,
    SCOPE_MILESTONE_CREATE,
    SCOPE_MILESTONE_DELETE,
    SCOPE_MILESTONE_EDIT,
    SCOPE_MILESTONE_REORDER,
)
from app.services.access import assert_project_active
from app.services.workflow.authorize import assert_capability
from app.services.features import CANCELLABLE_TASK_STATES, cancel_feature_cascade

WORK_ACTIVE_FEATURE = frozenset(
    {
        "en_progreso",
        "uat",
        "esperando_liberacion_pm",
        "esperando_validacion_cliente",
    }
)
TERMINAL_FEATURE = frozenset({"completado", "cancelado"})


def _ordered_milestones(db: Session, project_id: uuid.UUID) -> list[Milestone]:
    return list(
        db.scalars(
            select(Milestone)
            .where(Milestone.project_id == project_id)
            .order_by(Milestone.orden.asc(), Milestone.created_at.asc())
        )
    )


def compact_milestone_ordenes(db: Session, project_id: uuid.UUID) -> None:
    """Renumerar hitos 1..N tras borrados o datos legacy con huecos."""
    for index, milestone in enumerate(_ordered_milestones(db, project_id), start=1):
        if milestone.orden != index:
            milestone.orden = index


def next_milestone_orden(db: Session, project_id: uuid.UUID) -> int:
    count = db.scalar(
        select(func.count())
        .select_from(Milestone)
        .where(Milestone.project_id == project_id)
    )
    return int(count or 0) + 1


def reorder_milestone(
    db: Session,
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    target_orden: int,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    rows = _ordered_milestones(db, project_id)
    moving = next((m for m in rows if m.id == milestone_id), None)
    if moving is None:
        return

    previous = moving.orden
    remaining = [m for m in rows if m.id != milestone_id]
    slot = max(1, min(target_orden, len(remaining) + 1))
    remaining.insert(slot - 1, moving)

    for index, milestone in enumerate(remaining, start=1):
        if milestone.orden == index:
            continue
        milestone.orden = index
        if milestone.id == moving.id:
            record_audit_log(
                db,
                project_id=project_id,
                user_id=actor_user_id,
                entidad_tipo="milestone",
                entidad_id=milestone.id,
                accion="updated",
                campo="orden",
                valor_anterior=str(previous),
                valor_nuevo=str(index),
            )


def compute_milestone_target_state(
    milestone: Milestone,
    features: list[Feature],
    *,
    project: Project,
) -> str | None:
    if project.estado != "activo" or milestone.estado == "cancelado":
        return None
    if not features:
        return None

    open_bugs = [
        f for f in features if f.tipo == "bug" and f.estado not in TERMINAL_FEATURE
    ]
    if open_bugs:
        nuevo = (
            "cerrado_con_bug"
            if date.today() > milestone.fecha_fin
            else "en_progreso_con_bug"
        )
    elif any(f.estado in WORK_ACTIVE_FEATURE for f in features):
        nuevo = "en_progreso"
    elif all(f.estado in TERMINAL_FEATURE for f in features):
        nuevo = "completado"
    else:
        nuevo = "pendiente"

    if milestone.estado == nuevo:
        return None
    return nuevo


def sync_milestone_state(
    db: Session,
    milestone: Milestone,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> bool:
    from app.services.workflow.engine import apply_entity_transition

    features = list(
        db.scalars(select(Feature).where(Feature.milestone_id == milestone.id))
    )
    nuevo = compute_milestone_target_state(milestone, features, project=project)
    if nuevo is None:
        return False

    apply_entity_transition(
        db,
        project,
        milestone,
        entity_type="milestone",
        action_id="sync",
        actor_user_id=actor_user_id,
        target_state=nuevo,
    )
    return True


def update_milestone(
    db: Session,
    milestone: Milestone,
    project: Project,
    payload: MilestoneUpdate,
) -> None:
    assert_project_active(project)
    assert_capability(db, project.id, payload.actor_user_id, SCOPE_MILESTONE_EDIT)
    if milestone.estado == "cancelado":
        raise HTTPException(
            status_code=409,
            detail="El hito está cancelado; no se puede editar",
        )

    changes = payload.model_dump(exclude_unset=True, exclude={"actor_user_id"})
    if not changes:
        return

    fecha_inicio = changes.get("fecha_inicio", milestone.fecha_inicio)
    fecha_fin = changes.get("fecha_fin", milestone.fecha_fin)
    if fecha_fin < fecha_inicio:
        raise HTTPException(
            status_code=422,
            detail="fecha_fin debe ser mayor o igual que fecha_inicio",
        )

    fecha_changed = "fecha_inicio" in changes or "fecha_fin" in changes
    new_orden = changes.pop("orden", None)

    if "estado" in changes:
        raise HTTPException(
            status_code=422,
            detail="El estado del hito se deriva del workflow; no se puede editar directamente",
        )

    for field, nuevo in changes.items():
        anterior = getattr(milestone, field)
        if anterior == nuevo:
            continue
        setattr(milestone, field, nuevo)
        accion = "estado_changed" if field == "estado" else "updated"
        record_audit_log(
            db,
            project_id=project.id,
            user_id=payload.actor_user_id,
            entidad_tipo="milestone",
            entidad_id=milestone.id,
            accion=accion,
            campo=field,
            valor_anterior=str(anterior),
            valor_nuevo=str(nuevo),
        )

    if new_orden is not None and new_orden != milestone.orden:
        reorder_milestone(
            db,
            project.id,
            milestone.id,
            new_orden,
            actor_user_id=payload.actor_user_id,
        )

    if fecha_changed:
        sync_milestone_state(
            db, milestone, project, actor_user_id=payload.actor_user_id
        )


def cancel_milestone_cascade(
    db: Session,
    milestone: Milestone,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    from app.services.workflow.engine import apply_entity_transition

    assert_project_active(project)
    assert_capability(db, project.id, actor_user_id, SCOPE_MILESTONE_CANCEL)

    if milestone.estado == "cancelado":
        return

    apply_entity_transition(
        db,
        project,
        milestone,
        entity_type="milestone",
        action_id="cancelar",
        actor_user_id=actor_user_id,
    )


def sync_milestone_states_for_project(
    db: Session,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> int:
    """Job diario / manual: recalcula estados de hitos (§4.4 plazos bug)."""
    if project.estado != "activo":
        return 0

    updated = 0
    milestones = list(
        db.scalars(
            select(Milestone).where(
                Milestone.project_id == project.id,
                Milestone.estado != "cancelado",
            )
        )
    )
    for milestone in milestones:
        if sync_milestone_state(
            db, milestone, project, actor_user_id=actor_user_id
        ):
            updated += 1
    return updated


def sync_all_milestone_states(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> int:
    stmt = select(Project).where(Project.estado == "activo")
    if project_id is not None:
        stmt = stmt.where(Project.id == project_id)
    total = 0
    for project in db.scalars(stmt):
        total += sync_milestone_states_for_project(
            db, project, actor_user_id=actor_user_id
        )
    return total
