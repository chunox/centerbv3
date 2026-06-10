"""Workflow de features: sync dev, UAT, aprobación y cancelación (§5.1–§5.6)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.entities import Feature, Milestone, Project, ProjectMember, Task
from app.schemas.features import FeatureUpdate
from app.services.audit import record_audit_log
from app.domain.capabilities import SCOPE_FEATURE_EDIT, SCOPE_FEATURE_MIGRATE
from app.services.feature_queries import assert_project_active
from app.services.workflow.authorize import assert_capability
from app.services.notifications import create_notification

FeatureAction = Literal[
    "pasar_a_uat",
    "cancelar",
    "enviar_al_pm",
    "devolver_rework",
    "liberar_cliente",
    "rechazar_liberacion",
    "confirmar",
    "no_funciona",
    "completar",
]

MemberRol = Literal["pm", "dev", "qa", "cliente"]

WORK_ACTIVE_FEATURE = frozenset(
    {
        "en_progreso",
        "uat",
        "esperando_liberacion_pm",
        "esperando_validacion_cliente",
    }
)
FROZEN_DEV_SYNC = frozenset(
    {
        "esperando_liberacion_pm",
        "esperando_validacion_cliente",
        "completado",
        "cancelado",
    }
)
CANCELLABLE_TASK_STATES = frozenset(
    {"backlog", "to_do", "in_progress", "ready_for_test"}
)
BLOCKED_WHEN_BLOQUEADA: frozenset[FeatureAction] = frozenset(
    {
        "pasar_a_uat",
        "enviar_al_pm",
        "devolver_rework",
        "liberar_cliente",
        "rechazar_liberacion",
        "confirmar",
        "no_funciona",
        "completar",
    }
)


def load_active_tasks(db: Session, feature_id: uuid.UUID) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(Task.feature_id == feature_id, Task.estado != "cancel")
            .order_by(Task.created_at.asc())
        )
    )


def compute_dev_feature_estado(feature: Feature, tasks: list[Task]) -> str | None:
    """Nuevo estado dev o None si no debe cambiar (§5.4 / §5.5)."""
    if feature.estado in FROZEN_DEV_SYNC:
        return None
    if feature.bloqueada:
        return None

    active = [t for t in tasks if t.estado != "cancel"]
    if not active:
        return "pendiente"
    if all(t.estado == "backlog" for t in active):
        return "pendiente"

    if feature.estado == "uat":
        if any(t.estado not in ("ready_for_test", "completed") for t in active):
            return "en_progreso"
        return None

    return "en_progreso"


def uat_gate_status(feature: Feature, tasks: list[Task]) -> dict:
    active = [t for t in tasks if t.estado != "cancel"]
    reasons: list[str] = []
    if feature.estado != "en_progreso":
        reasons.append("La feature debe estar en en_progreso")
    if feature.bloqueada:
        reasons.append("La feature está bloqueada por consultas activas")
    if not active:
        reasons.append("Se requiere al menos una tarea activa")
    elif not all(t.estado == "ready_for_test" for t in active):
        reasons.append("Todas las tareas activas deben estar en ready_for_test")

    return {
        "can_pass_to_uat": len(reasons) == 0,
        "active_tasks": len(active),
        "ready_for_test_tasks": sum(1 for t in active if t.estado == "ready_for_test"),
        "bloqueada": feature.bloqueada,
        "estado": feature.estado,
        "reasons": reasons,
    }


def _set_feature_estado(
    db: Session,
    feature: Feature,
    project: Project,
    *,
    nuevo: str,
    actor_user_id: uuid.UUID,
    origen: str,
) -> None:
    anterior = feature.estado
    if anterior == nuevo:
        return
    feature.estado = nuevo
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="feature",
        entidad_id=feature.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior=anterior,
        valor_nuevo=f"{nuevo} ({origen})",
    )


_ROLE_NOTIFY_CAPABILITY: dict[str, str] = {
    "pm": "workbench.inbox.pm",
    "dev": "workbench.inbox.dev",
    "qa": "workbench.inbox.qa",
    "cliente": "workbench.inbox.client",
}


def _notify_role(
    db: Session,
    project: Project,
    *,
    rol: str,
    tipo: str,
    entidad_id: uuid.UUID,
) -> None:
    from app.services.workflow.capabilities import users_with_capability

    cap = _ROLE_NOTIFY_CAPABILITY.get(rol)
    if cap is None:
        return
    for user_id in users_with_capability(db, project.id, cap):
        create_notification(
            db,
            user_id=user_id,
            project_id=project.id,
            tipo=tipo,  # type: ignore[arg-type]
            entidad_tipo="feature",
            entidad_id=entidad_id,
        )


def ensure_default_task(
    db: Session, feature: Feature, *, created_by: uuid.UUID
) -> Task | None:
    has_tasks = db.scalar(
        select(exists().where(Task.feature_id == feature.id))
    )
    if has_tasks:
        return None
    task = Task(
        feature_id=feature.id,
        project_id=feature.project_id,
        titulo="Tarea inicial",
        estado="backlog",
        created_by=created_by,
    )
    db.add(task)
    return task


def sync_feature_from_tasks(
    db: Session,
    feature: Feature,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> bool:
    """Recalcula pendiente/en_progreso (y baja de uat). Devuelve True si cambió."""
    assert_project_active(project)
    if feature.estado in FROZEN_DEV_SYNC:
        return False
    if feature.bloqueada:
        return False

    tasks = load_active_tasks(db, feature.id)
    nuevo = compute_dev_feature_estado(feature, tasks)
    if nuevo is None or nuevo == feature.estado:
        return False

    was_pendiente = feature.estado == "pendiente"
    _set_feature_estado(
        db, feature, project, nuevo=nuevo, actor_user_id=actor_user_id, origen="sync_tareas"
    )
    if was_pendiente and nuevo == "en_progreso":
        _notify_role(
            db,
            project,
            rol="pm",
            tipo="estado_changed",
            entidad_id=feature.id,
        )
    milestone = db.get(Milestone, feature.milestone_id)
    if milestone:
        from app.services.milestones import sync_milestone_state

        sync_milestone_state(db, milestone, project, actor_user_id=actor_user_id)
    return True


def cancel_feature_cascade(
    db: Session,
    feature: Feature,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    if feature.estado != "cancelado":
        _set_feature_estado(
            db,
            feature,
            project,
            nuevo="cancelado",
            actor_user_id=actor_user_id,
            origen="cancelar",
        )
        record_audit_log(
            db,
            project_id=project.id,
            user_id=actor_user_id,
            entidad_tipo="feature",
            entidad_id=feature.id,
            accion="cancelada",
        )
    for task in db.scalars(select(Task).where(Task.feature_id == feature.id)):
        if task.estado in CANCELLABLE_TASK_STATES:
            prev = task.estado
            task.estado = "cancel"
            record_audit_log(
                db,
                project_id=project.id,
                user_id=actor_user_id,
                entidad_tipo="tarea",
                entidad_id=task.id,
                accion="estado_changed",
                campo="estado",
                valor_anterior=prev,
                valor_nuevo="cancel (cascada_feature)",
            )
    milestone = db.get(Milestone, feature.milestone_id)
    if milestone:
        from app.services.milestones import sync_milestone_state

        sync_milestone_state(db, milestone, project, actor_user_id=actor_user_id)


def apply_feature_action(
    db: Session,
    feature: Feature,
    project: Project,
    *,
    action: FeatureAction,
    actor_user_id: uuid.UUID,
    form_data: dict | None = None,
) -> None:
    from app.services.workflow.engine import apply_entity_transition

    assert_project_active(project)
    if action in BLOCKED_WHEN_BLOQUEADA and feature.bloqueada:
        raise HTTPException(
            status_code=409,
            detail="La feature está bloqueada por consultas activas",
        )

    apply_entity_transition(
        db,
        project,
        feature,
        entity_type="feature",
        action_id=action,
        actor_user_id=actor_user_id,
        form_data=form_data,
    )
    milestone = db.get(Milestone, feature.milestone_id)
    if milestone:
        from app.services.milestones import sync_milestone_state

        sync_milestone_state(db, milestone, project, actor_user_id=actor_user_id)


def _rework_from_pm_cliente(
    db: Session,
    feature: Feature,
    project: Project,
    tasks: list[Task],
    *,
    actor_user_id: uuid.UUID,
) -> None:
    for task in tasks:
        if task.estado == "completed":
            prev = task.estado
            task.estado = "in_progress"
            record_audit_log(
                db,
                project_id=project.id,
                user_id=actor_user_id,
                entidad_tipo="tarea",
                entidad_id=task.id,
                accion="estado_changed",
                campo="estado",
                valor_anterior=prev,
                valor_nuevo="in_progress (rework_aprobacion)",
            )
    _set_feature_estado(
        db,
        feature,
        project,
        nuevo="en_progreso",
        actor_user_id=actor_user_id,
        origen="rework_aprobacion",
    )
    _notify_role(
        db, project, rol="dev", tipo="estado_changed", entidad_id=feature.id
    )


def update_feature(
    db: Session,
    feature: Feature,
    project: Project,
    payload: FeatureUpdate,
) -> None:
    assert_project_active(project)
    assert_capability(db, project.id, payload.actor_user_id, SCOPE_FEATURE_EDIT)

    changes = payload.model_dump(exclude_unset=True, exclude={"actor_user_id"})
    if not changes:
        return

    fecha_inicio = changes.get("fecha_inicio", feature.fecha_inicio)
    fecha_fin = changes.get("fecha_fin", feature.fecha_fin)
    if fecha_fin < fecha_inicio:
        raise HTTPException(
            status_code=422,
            detail="fecha_fin debe ser mayor o igual que fecha_inicio",
        )

    if feature.tipo == "mejora":
        duracion = changes.get("duracion_estimada", feature.duracion_estimada)
        if duracion is None:
            raise HTTPException(
                status_code=422,
                detail="duracion_estimada es obligatoria para tipo mejora",
            )

    for field, nuevo in changes.items():
        anterior = getattr(feature, field)
        if anterior == nuevo:
            continue
        setattr(feature, field, nuevo)
        record_audit_log(
            db,
            project_id=project.id,
            user_id=payload.actor_user_id,
            entidad_tipo="feature",
            entidad_id=feature.id,
            accion="updated",
            campo=field,
            valor_anterior=str(anterior) if anterior is not None else None,
            valor_nuevo=str(nuevo) if nuevo is not None else None,
        )


def migrate_feature(
    db: Session,
    feature: Feature,
    project: Project,
    source_milestone: Milestone,
    target_milestone: Milestone,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_capability(db, project.id, actor_user_id, SCOPE_FEATURE_MIGRATE)

    if feature.tipo in ("bug", "mejora"):
        raise HTTPException(
            status_code=409,
            detail="Las features bug/mejora no se pueden migrar entre hitos",
        )
    if target_milestone.estado == "cancelado":
        raise HTTPException(
            status_code=409,
            detail="No se puede migrar a un hito cancelado",
        )
    if target_milestone.id == source_milestone.id:
        raise HTTPException(
            status_code=400,
            detail="La feature ya pertenece a ese hito",
        )

    anterior = str(source_milestone.id)
    feature.milestone_id = target_milestone.id
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="feature",
        entidad_id=feature.id,
        accion="migrada",
        campo="milestone_id",
        valor_anterior=anterior,
        valor_nuevo=str(target_milestone.id),
    )
    from app.services.milestones import sync_milestone_state

    sync_milestone_state(
        db, source_milestone, project, actor_user_id=actor_user_id
    )
    sync_milestone_state(
        db, target_milestone, project, actor_user_id=actor_user_id
    )
