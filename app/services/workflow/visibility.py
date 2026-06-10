"""Visibilidad de lectura basada en capacidades."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.capabilities import (
    AUDIT_VIEW_ALL,
    AUDIT_VIEW_SCOPED,
    DOCUMENT_VIEW_INTERNAL,
    KANBAN_VIEW,
    REPORT_CREATE,
    WORKBENCH_INBOX_CLIENT,
    WORKBENCH_UAT,
)
from app.models.entities import AuditLog, Feature, FeatureReport, TaskAssignee
from app.services.workflow.capabilities import get_effective_capabilities, user_has_capability


def filter_audit_logs_for_capabilities(
    db: Session,
    logs: list[AuditLog],
    *,
    project_id: uuid.UUID,
    viewer_user_id: uuid.UUID | None,
) -> list[AuditLog]:
    if viewer_user_id is None:
        return logs
    if user_has_capability(db, project_id, viewer_user_id, AUDIT_VIEW_ALL):
        return logs
    if not user_has_capability(db, project_id, viewer_user_id, AUDIT_VIEW_SCOPED):
        return []

    caps = get_effective_capabilities(db, project_id, viewer_user_id)
    allowed_types = _audit_entity_types_for_capabilities(caps)
    if not allowed_types:
        return []

    is_dev_scope = KANBAN_VIEW in caps
    is_qa_scope = WORKBENCH_UAT in caps
    is_client_scope = WORKBENCH_INBOX_CLIENT in caps or REPORT_CREATE in caps

    assigned_task_ids: set[uuid.UUID] | None = None
    own_report_ids: set[uuid.UUID] | None = None
    if is_dev_scope:
        assigned_task_ids = set(
            db.scalars(
                select(TaskAssignee.task_id).where(
                    TaskAssignee.user_id == viewer_user_id
                )
            )
        )
    if is_client_scope:
        own_report_ids = set(
            db.scalars(
                select(FeatureReport.id).where(
                    FeatureReport.reported_by == viewer_user_id
                )
            )
        )

    filtered: list[AuditLog] = []
    for log in logs:
        if log.entidad_tipo not in allowed_types:
            continue
        if is_dev_scope:
            if log.user_id == viewer_user_id:
                filtered.append(log)
                continue
            if log.entidad_tipo == "tarea" and assigned_task_ids:
                if log.entidad_id in assigned_task_ids:
                    filtered.append(log)
                continue
            if log.entidad_tipo in ("feature", "comment"):
                filtered.append(log)
            continue
        if is_qa_scope:
            if log.entidad_tipo == "feature":
                feature = db.get(Feature, log.entidad_id)
                if feature and feature.estado in (
                    "uat",
                    "esperando_liberacion_pm",
                    "esperando_validacion_cliente",
                    "completado",
                ):
                    filtered.append(log)
                continue
            filtered.append(log)
            continue
        if is_client_scope:
            if log.user_id == viewer_user_id:
                filtered.append(log)
                continue
            if log.entidad_tipo == "feature_report" and own_report_ids:
                if log.entidad_id in own_report_ids:
                    filtered.append(log)
                continue
            if log.entidad_tipo in ("feature", "feature_query", "comment"):
                filtered.append(log)
            continue
        filtered.append(log)

    return filtered


def _audit_entity_types_for_capabilities(caps: frozenset[str]) -> frozenset[str]:
    types: set[str] = set()
    if KANBAN_VIEW in caps:
        types.update({"feature", "tarea", "comment"})
    if WORKBENCH_UAT in caps:
        types.update({"feature", "tarea", "comment"})
    if WORKBENCH_INBOX_CLIENT in caps or REPORT_CREATE in caps:
        types.update({"feature", "feature_query", "feature_report", "comment"})
    return frozenset(types)


def hub_entry_visible_to_capabilities(
    db: Session,
    project_id: uuid.UUID,
    viewer_user_id: uuid.UUID | None,
    visibilidad: str,
) -> bool:
    if visibilidad == "publico":
        return True
    if viewer_user_id is None:
        return True
    return user_has_capability(db, project_id, viewer_user_id, DOCUMENT_VIEW_INTERNAL)


def comment_visible_for_capabilities(
    db: Session,
    project_id: uuid.UUID,
    *,
    viewer_user_id: uuid.UUID | None,
    entidad_tipo: str,
    comment_user_id: uuid.UUID,
) -> bool:
    if viewer_user_id is None:
        return True
    if user_has_capability(db, project_id, viewer_user_id, AUDIT_VIEW_ALL):
        return True
    if not user_has_capability(db, project_id, viewer_user_id, AUDIT_VIEW_SCOPED):
        return False
    caps = get_effective_capabilities(db, project_id, viewer_user_id)
    allowed = _audit_entity_types_for_capabilities(caps)
    if entidad_tipo not in allowed:
        return False
    if comment_user_id == viewer_user_id:
        return True
    return entidad_tipo in allowed


def document_visible_to_capabilities(
    db: Session,
    project_id: uuid.UUID,
    viewer_user_id: uuid.UUID | None,
    visibilidad: str,
) -> bool:
    if visibilidad == "publico":
        return True
    if viewer_user_id is None:
        return True
    return user_has_capability(db, project_id, viewer_user_id, DOCUMENT_VIEW_INTERNAL)
