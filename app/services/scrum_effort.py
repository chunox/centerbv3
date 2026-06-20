"""Esfuerzo Scrum: rollup horas (story tasks + dev tasks)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.services.records.repository import list_children, update_record_fields
from app.domain.project_mode import is_scrum_mode
from app.services.scrum_v2_structure import (
    get_product_backlog_record,
    is_scrum_story,
    is_sprint_record,
    list_stories_for_sprint,
)

TASK_CANCEL_STATE = "cancel"


def is_scrum_project(project: Project) -> bool:
    return is_scrum_mode(project)


def _hours_value(raw: Any) -> float:
    if raw is None:
        return 0.0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, val)


def get_scrum_item_sprint_id(db: Session, record: ProjectRecord) -> uuid.UUID | None:
    """Sprint id si el item está comprometido (historia o dev vía parent_id, o legacy data.sprint_id)."""
    if record.parent_id:
        parent = db.get(ProjectRecord, record.parent_id)
        if parent is not None and is_sprint_record(parent):
            return parent.id
    raw = (record.data or {}).get("sprint_id")
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


def get_feature_sprint_id(record: ProjectRecord) -> uuid.UUID | None:
    """Legacy: sprint_id en data (features). Preferir get_scrum_item_sprint_id con db."""
    raw = (record.data or {}).get("sprint_id")
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


def compute_feature_effort_hours(db: Session, record_id: uuid.UUID) -> float:
    from app.services.scrum_tasks import batch_story_effort_hours

    row = db.get(ProjectRecord, record_id)
    if row is not None and is_scrum_story(row):
        return batch_story_effort_hours(db, row.project_id, [record_id]).get(record_id, 0.0)
    tasks = list_children(db, record_id, "task")
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
    from app.services.scrum_tasks import batch_story_effort_hours

    rows = [db.get(ProjectRecord, fid) for fid in feature_ids]
    story_ids = [r.id for r in rows if r is not None and is_scrum_story(r)]
    if story_ids and len(story_ids) == len(feature_ids):
        return batch_story_effort_hours(db, project_id, story_ids)

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


def batch_story_effort_hours(
    db: Session,
    project_id: uuid.UUID,
    story_ids: list[uuid.UUID],
) -> dict[uuid.UUID, float]:
    """Alias Scrum: historias (tasks) en lugar de features waterfall."""
    return batch_feature_effort_hours(db, project_id, story_ids)


def get_story_sprint_id(db: Session, record: ProjectRecord) -> uuid.UUID | None:
    """Alias Scrum: sprint vía parent_id de historia."""
    return get_scrum_item_sprint_id(db, record)


def sync_feature_dates_from_sprint(
    db: Session,
    record: ProjectRecord,
    sprint: ProjectRecord,
) -> bool:
    if not is_sprint_record(sprint):
        return False
    if record.record_type not in ("feature", "task"):
        return False
    if (
        record.fecha_inicio == sprint.fecha_inicio
        and record.fecha_fin == sprint.fecha_fin
    ):
        return False
    update_record_fields(
        db,
        record,
        fecha_inicio=sprint.fecha_inicio,
        fecha_fin=sprint.fecha_fin,
    )
    return True


def propagate_sprint_dates_to_features(db: Session, sprint: ProjectRecord) -> int:
    if not is_sprint_record(sprint):
        return 0
    updated = 0
    for story in list_stories_for_sprint(db, sprint.project_id, sprint.id):
        if sync_feature_dates_from_sprint(db, story, sprint):
            updated += 1
    return updated


def maybe_sync_scrum_on_sprint_assignment(
    db: Session,
    project: Project,
    record: ProjectRecord,
) -> None:
    if not is_scrum_project(project):
        return
    sprint_id: uuid.UUID | None = None
    if record.record_type == "task" and is_scrum_story(record) and record.parent_id:
        parent = db.get(ProjectRecord, record.parent_id)
        if parent is not None and is_sprint_record(parent):
            sprint_id = parent.id
    elif record.record_type == "feature":
        raw = (record.data or {}).get("sprint_id")
        if raw not in (None, ""):
            try:
                sprint_id = uuid.UUID(str(raw))
            except (TypeError, ValueError):
                return
    if sprint_id is None:
        return
    sprint = db.get(ProjectRecord, sprint_id)
    if sprint is None or not is_sprint_record(sprint):
        return
    sync_feature_dates_from_sprint(db, record, sprint)


def maybe_propagate_scrum_sprint_dates(
    db: Session,
    project: Project,
    sprint: ProjectRecord,
    *,
    fecha_changed: bool,
) -> None:
    if not is_scrum_project(project) or not fecha_changed:
        return
    if not is_sprint_record(sprint):
        return
    propagate_sprint_dates_to_features(db, sprint)


def is_record_in_product_backlog(db: Session, record: ProjectRecord) -> bool:
    from app.services.scrum_v2_structure import is_scrum_dev_task, is_scrum_epic_task, is_scrum_story

    if is_scrum_epic_task(record) or is_scrum_dev_task(record):
        return False
    if is_scrum_story(record):
        backlog = get_product_backlog_record(db, record.project_id)
        return backlog is not None and record.parent_id == backlog.id
    raw = (record.data or {}).get("sprint_id")
    return raw is None or raw == ""
