"""Workflow de features: sync dev, UAT, aprobación y cancelación (§5.1–§5.6)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.capabilities import SCOPE_FEATURE_EDIT, SCOPE_FEATURE_MIGRATE
from app.domain.records.types import RecordRef
from app.models.entities import Project, ProjectRecord
from app.schemas.features import FeatureUpdate
from app.services.access import assert_project_active
from app.services.audit import record_audit_log
from app.services.notifications import create_notification
from app.services.records.repository import (
    _data,
    create_record,
    get_field,
    list_children,
    set_field,
    update_record_fields,
)
from app.services.scrum_effort import is_scrum_project
from app.services.workflow.authorize import assert_capability
from app.services.workflow.categories import (
    is_task_cancel_state,
    resolve_workflow,
    task_backlog_state_keys,
    task_cancellable_state_keys,
    task_cancel_state_keys,
    task_done_state_keys,
    task_test_state_keys,
)

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


def _feature_bloqueada(feature: ProjectRecord) -> bool:
    return bool(_data(feature).get("bloqueada", False))


def _feature_tipo(feature: ProjectRecord) -> str:
    return str(_data(feature).get("tipo", "desarrollo"))


def load_active_tasks(
    db: Session,
    feature_id: uuid.UUID,
    *,
    task_workflow: dict | None = None,
) -> list[ProjectRecord]:
    tasks = list_children(db, feature_id, "task")
    wf = task_workflow or {}
    active = [t for t in tasks if not is_task_cancel_state(wf, t.estado)]
    return sorted(active, key=lambda t: t.created_at)


def compute_dev_feature_estado(
    feature: ProjectRecord,
    tasks: list[ProjectRecord],
    *,
    task_workflow: dict | None = None,
) -> str | None:
    """Nuevo estado dev o None si no debe cambiar (§5.4 / §5.5)."""
    wf = task_workflow or {}
    cancel_keys = task_cancel_state_keys(wf)
    backlog_keys = task_backlog_state_keys(wf)
    test_keys = task_test_state_keys(wf)
    done_keys = task_done_state_keys(wf)
    allowed_uat = test_keys | done_keys

    if feature.estado in FROZEN_DEV_SYNC:
        return None
    if _feature_bloqueada(feature):
        return None

    active = [t for t in tasks if t.estado not in cancel_keys]
    if not active:
        return "pendiente"
    if all(t.estado in backlog_keys for t in active):
        return "pendiente"

    if feature.estado == "uat":
        if any(t.estado not in allowed_uat for t in active):
            return "en_progreso"
        return None

    return "en_progreso"


def uat_gate_status(
    feature: ProjectRecord,
    tasks: list[ProjectRecord],
    *,
    task_workflow: dict | None = None,
) -> dict[str, Any]:
    wf = task_workflow or {}
    cancel_keys = task_cancel_state_keys(wf)
    test_keys = task_test_state_keys(wf)
    active = [t for t in tasks if t.estado not in cancel_keys]
    reasons: list[str] = []
    if feature.estado != "en_progreso":
        reasons.append("La feature debe estar en en_progreso")
    if _feature_bloqueada(feature):
        reasons.append("La feature está bloqueada por consultas activas")
    if not active:
        reasons.append("Se requiere al menos una tarea activa")
    elif not all(t.estado in test_keys for t in active):
        test_label = ", ".join(sorted(test_keys)) or "test"
        reasons.append(f"Todas las tareas activas deben estar en {test_label}")

    return {
        "can_pass_to_uat": len(reasons) == 0,
        "active_tasks": len(active),
        "ready_for_test_tasks": sum(1 for t in active if t.estado in test_keys),
        "bloqueada": _feature_bloqueada(feature),
        "estado": feature.estado,
        "reasons": reasons,
    }


def _set_feature_estado(
    db: Session,
    feature: ProjectRecord,
    project: Project,
    *,
    nuevo: str,
    actor_user_id: uuid.UUID,
    origen: str,
) -> None:
    anterior = feature.estado
    if anterior == nuevo:
        return
    update_record_fields(db, feature, estado=nuevo)
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
    db: Session, feature: ProjectRecord, *, created_by: uuid.UUID
) -> ProjectRecord | None:
    if list_children(db, feature.id, "task"):
        return None
    project = db.get(Project, feature.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return create_record(
        db,
        project,
        entity_type="task",
        titulo="Tarea inicial",
        created_by=created_by,
        parent_id=feature.id,
        estado="backlog",
    )


def sync_feature_from_tasks(
    db: Session,
    feature: ProjectRecord,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> bool:
    """Recalcula pendiente/en_progreso (y baja de uat). Devuelve True si cambió."""
    assert_project_active(project)
    if feature.estado in FROZEN_DEV_SYNC:
        return False
    if _feature_bloqueada(feature):
        return False

    tasks = load_active_tasks(
        db,
        feature.id,
        task_workflow=resolve_workflow(db, project.id, "task", project.profile_slug),
    )
    nuevo = compute_dev_feature_estado(
        feature,
        tasks,
        task_workflow=resolve_workflow(db, project.id, "task", project.profile_slug),
    )
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
    milestone_id = feature.parent_id
    if milestone_id:
        milestone = db.get(ProjectRecord, milestone_id)
        if milestone is not None:
            from app.services.milestones import sync_milestone_state

            sync_milestone_state(db, milestone, project, actor_user_id=actor_user_id)
    return True


def cancel_feature_cascade(
    db: Session,
    feature: ProjectRecord,
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
    cancellable = task_cancellable_state_keys(
        resolve_workflow(db, project.id, "task", project.profile_slug)
    )
    cancel_targets = task_cancel_state_keys(
        resolve_workflow(db, project.id, "task", project.profile_slug)
    )
    cancel_to = next(iter(cancel_targets), "cancel")
    for task in list_children(db, feature.id, "task"):
        if task.estado in cancellable:
            prev = task.estado
            update_record_fields(db, task, estado=cancel_to)
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
    milestone_id = feature.parent_id
    if milestone_id:
        milestone = db.get(ProjectRecord, milestone_id)
        if milestone is not None:
            from app.services.milestones import sync_milestone_state

            sync_milestone_state(db, milestone, project, actor_user_id=actor_user_id)


def apply_feature_action(
    db: Session,
    feature: ProjectRecord,
    project: Project,
    *,
    action: FeatureAction,
    actor_user_id: uuid.UUID,
    form_data: dict | None = None,
) -> None:
    from app.services.workflow.engine import apply_record_transition

    assert_project_active(project)
    if action in BLOCKED_WHEN_BLOQUEADA and _feature_bloqueada(feature):
        raise HTTPException(
            status_code=409,
            detail="La feature está bloqueada por consultas activas",
        )

    apply_record_transition(
        db,
        project,
        feature,
        record_ref=RecordRef(
            id=feature.id,
            record_type="feature",
            project_id=project.id,
        ),
        action_id=action,
        actor_user_id=actor_user_id,
        form_data=form_data,
    )
    milestone_id = feature.parent_id
    if milestone_id:
        milestone = db.get(ProjectRecord, milestone_id)
        if milestone is not None:
            from app.services.milestones import sync_milestone_state

            sync_milestone_state(db, milestone, project, actor_user_id=actor_user_id)


def _rework_from_pm_cliente(
    db: Session,
    feature: ProjectRecord,
    project: Project,
    tasks: list[ProjectRecord],
    *,
    actor_user_id: uuid.UUID,
) -> None:
    for task in tasks:
        if task.estado == "completed":
            prev = task.estado
            update_record_fields(db, task, estado="in_progress")
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
    feature: ProjectRecord,
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

    if _feature_tipo(feature) == "mejora" and not is_scrum_project(project):
        duracion = changes.get("duracion_estimada", get_field(feature, "duracion_estimada"))
        if duracion is None:
            raise HTTPException(
                status_code=422,
                detail="duracion_estimada es obligatoria para tipo mejora",
            )

    for field, nuevo in changes.items():
        if field == "nombre":
            anterior = feature.titulo
            if anterior == nuevo:
                continue
            update_record_fields(db, feature, titulo=nuevo)
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
        elif field == "descripcion":
            anterior = feature.descripcion
            if anterior == nuevo:
                continue
            update_record_fields(db, feature, descripcion=nuevo)
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
        elif field in ("fecha_inicio", "fecha_fin"):
            anterior = getattr(feature, field)
            if anterior == nuevo:
                continue
            update_record_fields(db, feature, **{field: nuevo})
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
        elif field in ("prioridad", "duracion_estimada"):
            anterior = get_field(feature, field)
            if anterior == nuevo:
                continue
            set_field(feature, field, nuevo)
            db.flush()
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
    feature: ProjectRecord,
    project: Project,
    source_milestone: ProjectRecord,
    target_milestone: ProjectRecord,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_capability(db, project.id, actor_user_id, SCOPE_FEATURE_MIGRATE)

    if _feature_tipo(feature) in ("bug", "mejora"):
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
    feature.parent_id = target_milestone.id
    db.flush()
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
