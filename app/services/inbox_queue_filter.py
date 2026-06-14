"""Filtrado de records por queue_filter de workbench (unificado)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.services.records.repository import list_records
from app.services.workflow.store import get_active_workflow, get_workbenches


def _state_category(
    db: Session,
    project: Project,
    record_type: str,
    estado: str,
) -> str | None:
    wf = get_active_workflow(db, project.id, record_type)
    if not wf:
        return None
    for state in wf.get("states") or []:
        if isinstance(state, dict) and state.get("key") == estado:
            return state.get("category")
    return None


def record_matches_queue_filter(
    db: Session,
    project: Project,
    record: ProjectRecord,
    queue_filter: dict[str, Any] | None,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> bool:
    if not queue_filter:
        return True

    entity_types = queue_filter.get("entity_types")
    if entity_types and record.record_type not in entity_types:
        return False

    state_categories = queue_filter.get("state_categories")
    include_states = queue_filter.get("include_states") or []
    if state_categories or include_states:
        category = _state_category(db, project, record.record_type, record.estado)
        if record.estado in include_states:
            pass
        elif state_categories and category in state_categories:
            pass
        else:
            return False

    created_by_actor = queue_filter.get("created_by_actor")
    if created_by_actor and actor_user_id is not None:
        if record.created_by != actor_user_id:
            return False

    return True


def list_inbox_records_for_workbench(
    db: Session,
    project: Project,
    workbench_key: str,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> list[ProjectRecord]:
    workbenches = get_workbenches(db, project.id)
    wb = next((w for w in workbenches if w.get("key") == workbench_key), None)
    if wb is None:
        return []

    queue_filter = wb.get("queue_filter")
    rows = list_records(db, project.id)
    matched = [
        r
        for r in rows
        if record_matches_queue_filter(
            db, project, r, queue_filter, actor_user_id=actor_user_id
        )
    ]
    matched.sort(key=lambda r: (r.updated_at, r.created_at), reverse=True)
    return matched


def count_inbox_for_workbench(
    db: Session,
    project: Project,
    workbench_key: str,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> int:
    return len(
        list_inbox_records_for_workbench(
            db, project, workbench_key, actor_user_id=actor_user_id
        )
    )


def build_counts_by_workbench(
    db: Session,
    project: Project,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> dict[str, int]:
    from app.services.workflow.store import get_workbenches

    workbenches = get_workbenches(db, project.id)
    counts: dict[str, int] = {}
    for wb in workbenches:
        key = wb.get("key")
        if not key or not wb.get("queue_filter"):
            continue
        actor = actor_user_id if wb.get("queue_filter", {}).get("created_by_actor") else None
        counts[key] = count_inbox_for_workbench(
            db, project, key, actor_user_id=actor
        )
    return counts


SOFTWARE_QUEUE_WORKBENCH: dict[str, str] = {
    "pm": "inbox_pm",
    "client": "inbox_client",
    "dev": "inbox_dev",
    "qa": "inbox_qa",
}
