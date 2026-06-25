"""Datos agregados para kanban y sprint board Scrum."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord
from app.schemas.records import RecordResponse
from app.services.records.store import _load_query, _to_response
from app.services.scrum.sprint_membership import get_active_sprint, parent_is_epic


def _scrum_role(record: ProjectRecord) -> str | None:
    return (record.extra or {}).get("scrum_role")


def _story_epic_id(story: ProjectRecord, epic_ids: set[str]) -> str | None:
    extra = story.extra or {}
    original = extra.get("original_parent_id")
    if original and str(original) in epic_ids:
        return str(original)
    if story.parent_id and str(story.parent_id) in epic_ids:
        return str(story.parent_id)
    return None


def _load_scrum_tasks(db: Session, project_id: str) -> list[ProjectRecord]:
    return (
        _load_query(db, project_id)
        .filter(ProjectRecord.record_type == "task")
        .order_by(ProjectRecord.orden)
        .all()
    )


def _epic_ids(tasks: list[ProjectRecord]) -> set[str]:
    return {str(t.id) for t in tasks if _scrum_role(t) == "epic"}


def _stories_for_workspace(
    tasks: list[ProjectRecord],
    epic_ids: set[str],
    target_sprint_id: str | None,
    db: Session,
) -> list[ProjectRecord]:
    stories: list[ProjectRecord] = []
    for t in tasks:
        if _scrum_role(t) != "story":
            continue
        in_backlog = parent_is_epic(db, t.parent_id)
        in_sprint = bool(target_sprint_id and str(t.parent_id) == target_sprint_id)
        if target_sprint_id:
            if in_sprint:
                stories.append(t)
        elif in_backlog:
            stories.append(t)
    return stories


def _epics_for_sprint_board(
    tasks: list[ProjectRecord],
    epic_ids: set[str],
    target_sprint_id: str | None,
    sprint_story_epic_ids: set[str],
) -> list[ProjectRecord]:
    if not target_sprint_id:
        return [t for t in tasks if _scrum_role(t) == "epic"]
    result: list[ProjectRecord] = []
    for t in tasks:
        if _scrum_role(t) != "epic":
            continue
        sid = (t.extra or {}).get("sprint_id")
        if sid and str(sid) == target_sprint_id:
            result.append(t)
        elif str(t.id) in sprint_story_epic_ids:
            result.append(t)
    return result


def _children_of_stories(
    tasks: list[ProjectRecord],
    story_ids: set[str],
) -> tuple[list[ProjectRecord], list[ProjectRecord]]:
    dev_tasks: list[ProjectRecord] = []
    subtasks: list[ProjectRecord] = []
    story_set = story_ids
    for t in tasks:
        role = _scrum_role(t)
        if role == "dev" and t.parent_id and str(t.parent_id) in story_set:
            dev_tasks.append(t)
    dev_ids = {str(d.id) for d in dev_tasks}
    for t in tasks:
        if _scrum_role(t) == "subtask" and t.parent_id and str(t.parent_id) in dev_ids:
            subtasks.append(t)
    return dev_tasks, subtasks


def build_scrum_workspace(
    db: Session,
    project_id: str,
    sprint_id: str | None = None,
) -> dict:
    active = get_active_sprint(db, project_id)
    target_sprint_id = sprint_id
    if target_sprint_id:
        sprint_record = (
            db.query(ProjectRecord)
            .filter(
                ProjectRecord.id == target_sprint_id,
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "sprint",
            )
            .first()
        )
        if not sprint_record:
            target_sprint_id = None
    elif active:
        target_sprint_id = str(active.id)

    tasks = _load_scrum_tasks(db, project_id)
    epic_ids = _epic_ids(tasks)
    stories = _stories_for_workspace(tasks, epic_ids, target_sprint_id, db)
    story_ids = {str(s.id) for s in stories}
    sprint_story_epic_ids = {
        eid for s in stories
        if target_sprint_id and str(s.parent_id) == target_sprint_id
        for eid in [_story_epic_id(s, epic_ids)]
        if eid
    }

    epics = _epics_for_sprint_board(tasks, epic_ids, target_sprint_id, sprint_story_epic_ids)
    if not target_sprint_id:
        epics = [t for t in tasks if _scrum_role(t) == "epic"]

    dev_tasks, subtasks = _children_of_stories(tasks, story_ids)

    def to_resp(r: ProjectRecord) -> RecordResponse:
        return _to_response(db, r)

    active_sprint_resp = None
    if active:
        active_sprint_resp = {
            "id": str(active.id),
            "title": active.title,
            "status": active.status,
            "goal": (active.extra or {}).get("goal"),
        }

    return {
        "active_sprint": active_sprint_resp,
        "sprint_id": target_sprint_id,
        "epics": [to_resp(e) for e in epics],
        "stories": [to_resp(s) for s in stories],
        "dev_tasks": [to_resp(d) for d in dev_tasks],
        "subtasks": [to_resp(st) for st in subtasks],
    }
