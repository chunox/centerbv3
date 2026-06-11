"""Registro de side-effects de workflow."""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Feature, FeatureReport, Milestone, Project
from app.services.audit import record_audit_log
from app.services.features import cancel_feature_cascade
from app.services.notifications import create_notification
from app.services.workflow.capabilities import users_with_capability

SideEffectHandler = Callable[
    [
        Session,
        Project,
        Any,
        str,
        str,
        uuid.UUID,
        dict[str, Any],
        dict[str, Any] | None,
        dict[str, Any] | None,
    ],
    None,
]

_HANDLERS: dict[str, SideEffectHandler] = {}


def register_side_effect(effect_type: str, handler: SideEffectHandler) -> None:
    _HANDLERS[effect_type] = handler


def run_side_effect(
    db: Session,
    *,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None = None,
    side_effect_context: dict[str, Any] | None = None,
    entidad_tipo: str,
) -> None:
    etype = effect.get("type")
    if not etype:
        return
    handler = _HANDLERS.get(etype)
    if handler is None:
        return
    handler(
        db,
        project,
        entity,
        entity_type,
        action_id,
        actor_user_id,
        effect,
        form_data,
        side_effect_context,
        entidad_tipo,
    )


def _handle_notify(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    cap = effect.get("target", {}).get("capability")
    if cap:
        for uid in users_with_capability(db, project.id, cap):
            create_notification(
                db,
                user_id=uid,
                project_id=project.id,
                tipo="estado_changed",
                entidad_tipo=entidad_tipo,  # type: ignore[arg-type]
                entidad_id=entity.id,
            )


def _handle_notify_reporter(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    if entity_type != "report" or not isinstance(entity, FeatureReport):
        return
    create_notification(
        db,
        user_id=entity.reported_by,
        project_id=project.id,
        tipo=effect.get("notification_tipo", "reporte_resuelto"),
        entidad_tipo="feature_report",
        entidad_id=entity.id,
    )


def _handle_generate_feature_from_report(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    if entity_type != "report" or not isinstance(entity, FeatureReport):
        return
    from app.services.feature_reports import generate_feature_from_report

    ctx = side_effect_context or {}
    milestone_id = ctx.get("milestone_id")
    if milestone_id is None:
        raise HTTPException(
            status_code=500,
            detail="milestone_id requerido para generate_feature_from_report",
        )
    milestone = db.get(Milestone, milestone_id)
    if milestone is None:
        raise HTTPException(status_code=404, detail="Hito no encontrado")
    original = db.get(Feature, entity.feature_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Feature original no encontrada")
    generate_feature_from_report(
        db,
        entity,
        original,
        project,
        milestone,
        actor_user_id=actor_user_id,
        form_data=form_data or ctx.get("form_data"),
    )


def _handle_sync_milestone_from_report(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    if entity_type != "report":
        return
    ctx = side_effect_context or {}
    milestone_id = ctx.get("milestone_id")
    if milestone_id is not None:
        milestone = db.get(Milestone, milestone_id)
        if milestone is not None:
            from app.services.milestones import sync_milestone_state

            sync_milestone_state(db, milestone, project, actor_user_id=actor_user_id)


def _handle_cancel_features_cascade(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    if entity_type != "milestone" or not isinstance(entity, Milestone):
        return
    features = list(db.scalars(select(Feature).where(Feature.milestone_id == entity.id)))
    for feature in features:
        if feature.estado != "cancelado":
            cancel_feature_cascade(db, feature, project, actor_user_id=actor_user_id)


def _handle_cancel_tasks_cascade(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    if entity_type == "feature":
        cancel_feature_cascade(db, entity, project, actor_user_id=actor_user_id)


def _handle_sync_tasks(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    if entity_type != "feature" or effect.get("rule") != "complete_ready_for_test":
        return
    from app.services.features import load_active_tasks

    tasks = load_active_tasks(db, entity.id)
    for task in tasks:
        if task.estado == "ready_for_test":
            prev = task.estado
            task.estado = "completed"
            record_audit_log(
                db,
                project_id=project.id,
                user_id=actor_user_id,
                entidad_tipo="tarea",
                entidad_id=task.id,
                accion="estado_changed",
                campo="estado",
                valor_anterior=prev,
                valor_nuevo="completed (workflow)",
            )


def _handle_rework_tasks(
    db: Session,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effect: dict[str, Any],
    form_data: dict[str, Any] | None,
    side_effect_context: dict[str, Any] | None,
    entidad_tipo: str,
) -> None:
    if entity_type != "feature":
        return
    from app.services.features import load_active_tasks

    tasks = load_active_tasks(db, entity.id)
    for task in tasks:
        if task.estado == "ready_for_test":
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
                valor_nuevo="in_progress (workflow_rework)",
            )


register_side_effect("notify", _handle_notify)
register_side_effect("notify_reporter", _handle_notify_reporter)
register_side_effect("generate_feature_from_report", _handle_generate_feature_from_report)
register_side_effect("sync_milestone_from_report", _handle_sync_milestone_from_report)
register_side_effect("cancel_features_cascade", _handle_cancel_features_cascade)
register_side_effect("cancel_tasks_cascade", _handle_cancel_tasks_cascade)
register_side_effect("sync_tasks", _handle_sync_tasks)
register_side_effect("rework_tasks", _handle_rework_tasks)
