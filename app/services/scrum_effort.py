"""Esfuerzo Scrum: rollup de horas por tarea y sync de fechas feature ← sprint."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.services.records.repository import list_children, update_record_fields

SCRUM_TEMPLATE_SLUGS = frozenset({"t6_scrum_interno", "t7_scrum_cliente"})
TASK_CANCEL_STATE = "cancel"


def is_scrum_project(project: Project) -> bool:
    return getattr(project, "template_slug", None) in SCRUM_TEMPLATE_SLUGS


def _hours_value(raw: Any) -> float:
    if raw is None:
        return 0.0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, val)


def compute_feature_effort_hours(db: Session, feature_id: uuid.UUID) -> float:
    tasks = list_children(db, feature_id, "task")
    total = 0.0
    for task in tasks:
        if task.estado == TASK_CANCEL_STATE:
            continue
        data = task.data if isinstance(task.data, dict) else {}
        total += _hours_value(data.get("estimacion_horas"))
    return total


def batch_feature_effort_hours(
    db: Session,
    project_id: uuid.UUID,
    feature_ids: list[uuid.UUID],
) -> dict[uuid.UUID, float]:
    if not feature_ids:
        return {}
    tasks = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "task",
                ProjectRecord.parent_id.in_(feature_ids),
                ProjectRecord.estado != TASK_CANCEL_STATE,
            )
        )
    )
    totals: dict[uuid.UUID, float] = {fid: 0.0 for fid in feature_ids}
    for task in tasks:
        if task.parent_id is None:
            continue
        data = task.data if isinstance(task.data, dict) else {}
        totals[task.parent_id] = totals.get(task.parent_id, 0.0) + _hours_value(
            data.get("estimacion_horas")
        )
    return totals


def sync_feature_dates_from_sprint(
    db: Session,
    feature: ProjectRecord,
    sprint: ProjectRecord,
) -> bool:
    """Copia fechas del sprint a la feature. Devuelve True si hubo cambio."""
    if feature.record_type != "feature" or sprint.record_type != "milestone":
        return False
    if (
        feature.fecha_inicio == sprint.fecha_inicio
        and feature.fecha_fin == sprint.fecha_fin
    ):
        return False
    update_record_fields(
        db,
        feature,
        fecha_inicio=sprint.fecha_inicio,
        fecha_fin=sprint.fecha_fin,
    )
    return True


def propagate_sprint_dates_to_features(db: Session, sprint: ProjectRecord) -> int:
    """Propaga fechas del sprint a todas las features hijas."""
    if sprint.record_type != "milestone":
        return 0
    updated = 0
    for feature in list_children(db, sprint.id, "feature"):
        if sync_feature_dates_from_sprint(db, feature, sprint):
            updated += 1
    return updated


def maybe_sync_scrum_on_feature_reparent(
    db: Session,
    project: Project,
    feature: ProjectRecord,
    *,
    new_parent_id: uuid.UUID | None,
) -> None:
    if not is_scrum_project(project) or feature.record_type != "feature":
        return
    if new_parent_id is None:
        return
    sprint = db.get(ProjectRecord, new_parent_id)
    if sprint is None or sprint.record_type != "milestone":
        return
    sync_feature_dates_from_sprint(db, feature, sprint)


def maybe_propagate_scrum_sprint_dates(
    db: Session,
    project: Project,
    sprint: ProjectRecord,
    *,
    fecha_changed: bool,
) -> None:
    if not is_scrum_project(project) or not fecha_changed:
        return
    if sprint.record_type != "milestone":
        return
    propagate_sprint_dates_to_features(db, sprint)
