"""Aplica opciones del modal G tras devolver una historia."""
from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app.domain.scrum.states import EXTRA_BLOCKED_BY_INHERITANCE, EXTRA_STATUS_BEFORE_BLOCK
from app.models.entities import Project, ProjectRecord
from app.services.scrum.descendants import collect_scrum_descendants

ChildrenOnReturn = Literal["unchanged", "return_to_backlog", "cancel"]

_SKIP_RETURN_STATUSES = frozenset({"backlog", "cancelled"})


def _scrub_block_extra(record: ProjectRecord) -> None:
    extra = dict(record.extra or {})
    extra.pop(EXTRA_STATUS_BEFORE_BLOCK, None)
    extra.pop(EXTRA_BLOCKED_BY_INHERITANCE, None)
    record.extra = extra


def _dev_subtask_descendants(db: Session, story: ProjectRecord) -> list[ProjectRecord]:
    descendants = collect_scrum_descendants(db, story, str(story.project_id))
    return [d for d in descendants if (d.extra or {}).get("scrum_role") in ("dev", "subtask")]


def apply_children_on_return(
    db: Session,
    story: ProjectRecord,
    project: Project,
    mode: ChildrenOnReturn,
    *,
    resolved_by: str | None = None,
) -> None:
    """Tras devolver historia: opcionalmente mover o cancelar devs/subtasks."""
    if mode == "unchanged":
        return
    if (story.extra or {}).get("scrum_role") != "story":
        return

    children = _dev_subtask_descendants(db, story)
    if not children:
        return

    if mode == "return_to_backlog":
        for child in children:
            if child.status in _SKIP_RETURN_STATUSES or child.status == "blocked":
                continue
            child.status = "backlog"
    elif mode == "cancel":
        from app.services.blockers import clear_blockers_on_record

        for child in children:
            if child.status == "cancelled":
                continue
            child.status = "cancelled"
            clear_blockers_on_record(db, str(child.id), resolved_by=resolved_by)
            _scrub_block_extra(child)

    db.flush()
