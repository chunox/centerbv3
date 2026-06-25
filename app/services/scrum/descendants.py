"""Descendientes Scrum por membership épica/historia (no solo parent_id)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord


def _children(db: Session, parent_id: str, project_id: str) -> list[ProjectRecord]:
    return (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.parent_id == parent_id,
            ProjectRecord.project_id == project_id,
        )
        .order_by(ProjectRecord.orden)
        .all()
    )


def _story_epic_id(story: ProjectRecord, epic_ids: set[str]) -> str | None:
    extra = story.extra or {}
    original = extra.get("original_parent_id")
    if original and str(original) in epic_ids:
        return str(original)
    if story.parent_id and str(story.parent_id) in epic_ids:
        return str(story.parent_id)
    return None


def _load_epic_ids(db: Session, project_id: str) -> set[str]:
    epics = (
        db.query(ProjectRecord)
        .filter(ProjectRecord.project_id == project_id, ProjectRecord.record_type == "task")
        .all()
    )
    return {str(e.id) for e in epics if (e.extra or {}).get("scrum_role") == "epic"}


def collect_scrum_descendants(
    db: Session,
    record: ProjectRecord,
    project_id: str,
) -> list[ProjectRecord]:
    """Recopila historias, dev tasks y subtareas bajo el record dado."""
    role = (record.extra or {}).get("scrum_role")
    if role not in ("epic", "story", "dev"):
        return []

    result: list[ProjectRecord] = []

    if role == "epic":
        epic_ids = _load_epic_ids(db, project_id)
        stories = (
            db.query(ProjectRecord)
            .filter(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "task",
            )
            .all()
        )
        epic_stories = [
            s for s in stories
            if (s.extra or {}).get("scrum_role") == "story"
            and _story_epic_id(s, epic_ids) == str(record.id)
        ]
        for story in epic_stories:
            result.append(story)
            for dev in _children(db, str(story.id), project_id):
                if (dev.extra or {}).get("scrum_role") != "dev":
                    continue
                result.append(dev)
                for sub in _children(db, str(dev.id), project_id):
                    if (sub.extra or {}).get("scrum_role") == "subtask":
                        result.append(sub)
    elif role == "story":
        for dev in _children(db, str(record.id), project_id):
            if (dev.extra or {}).get("scrum_role") != "dev":
                continue
            result.append(dev)
            for sub in _children(db, str(dev.id), project_id):
                if (sub.extra or {}).get("scrum_role") == "subtask":
                    result.append(sub)
    elif role == "dev":
        for sub in _children(db, str(record.id), project_id):
            if (sub.extra or {}).get("scrum_role") == "subtask":
                result.append(sub)

    return result


def stories_for_epic(db: Session, epic: ProjectRecord) -> list[ProjectRecord]:
    """Historias de la épica en cualquier membership (backlog o sprint)."""
    descendants = collect_scrum_descendants(db, epic, str(epic.project_id))
    return [d for d in descendants if (d.extra or {}).get("scrum_role") == "story"]
