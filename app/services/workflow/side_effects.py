"""
Side effects post-transición de workflow.

Ejecutados después de cambiar record.status en apply_transition.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord


DONE_TASK_STATES = frozenset({"done", "cancelled"})
DONE_FEATURE_STATES = frozenset({"done", "cancelled"})
ACTIVE_FEATURE_STATES = frozenset({"in_progress", "in_review"})
DONE_STORY_STATES = frozenset({"done", "cancelled"})


def _children(db: Session, parent_id: str, project_id: str) -> list[ProjectRecord]:
    return (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.parent_id == parent_id,
            ProjectRecord.project_id == project_id,
        )
        .all()
    )


def sync_parent_feature(db: Session, record: ProjectRecord, project: Project) -> None:
    """Recalcula status de la feature padre según tasks hijas."""
    if record.record_type != "task" or not record.parent_id:
        return
    feature = db.query(ProjectRecord).filter(ProjectRecord.id == record.parent_id).first()
    if not feature or feature.record_type != "feature":
        return

    tasks = _children(db, feature.id, str(project.id))
    if not tasks:
        return

    if all(t.status in DONE_TASK_STATES for t in tasks):
        if all(t.status == "cancelled" for t in tasks):
            feature.status = "cancelled"
        else:
            feature.status = "done"
    elif any(t.status in ("in_progress", "in_review", "to_do") for t in tasks):
        feature.status = "in_progress"
    db.flush()
    sync_parent_milestone(db, feature, project)


def sync_parent_milestone(db: Session, record: ProjectRecord, project: Project) -> None:
    """Recalcula status del milestone padre según features hijas."""
    if record.record_type != "feature" or not record.parent_id:
        return
    milestone = db.query(ProjectRecord).filter(ProjectRecord.id == record.parent_id).first()
    if not milestone or milestone.record_type != "milestone":
        return

    features = _children(db, milestone.id, str(project.id))
    if not features:
        return

    if all(f.status == "done" for f in features):
        milestone.status = "done"
    elif any(f.status in ACTIVE_FEATURE_STATES for f in features):
        milestone.status = "in_progress"
    elif all(f.status == "cancelled" for f in features):
        milestone.status = "cancelled"
    else:
        milestone.status = "backlog"
    db.flush()


def sync_from_features(db: Session, record: ProjectRecord, project: Project) -> None:
    """Al completar milestone manualmente, verifica consistencia con features."""
    if record.record_type != "milestone":
        return
    features = _children(db, record.id, str(project.id))
    if features and not all(f.status == "done" for f in features):
        record.status = "in_progress"
    db.flush()


def restore_story_to_backlog(story: ProjectRecord) -> None:
    """Devuelve una historia al backlog de su épica y limpia el vínculo al sprint."""
    extra = dict(story.extra or {})
    original_epic = extra.pop("original_parent_id", None)
    story.extra = extra
    if original_epic:
        story.parent_id = original_epic
    story.status = "backlog"


def reparent_to_sprint(db: Session, record: ProjectRecord, project: Project) -> None:
    """Story comprometida: parent_id → sprint activo."""
    scrum_role = (record.extra or {}).get("scrum_role")
    if scrum_role != "story":
        return
    active_sprint = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.project_id == str(project.id),
            ProjectRecord.record_type == "sprint",
            ProjectRecord.status == "activo",
        )
        .first()
    )
    if not active_sprint:
        return
    if record.parent_id != active_sprint.id:
        extra = {**(record.extra or {}), "original_parent_id": record.parent_id}
        record.extra = extra
        record.parent_id = active_sprint.id
    db.flush()


def resolve_incomplete_sprint_stories(
    db: Session,
    sprint: ProjectRecord,
    project_id: str,
    *,
    default_action: str = "backlog",
    resolution_map: dict[str, str] | None = None,
) -> None:
    """Mueve historias incompletas del sprint según la acción indicada."""
    incomplete = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.parent_id == sprint.id,
            ProjectRecord.project_id == project_id,
            ProjectRecord.status.notin_(list(DONE_STORY_STATES)),
        )
        .all()
    )
    resolutions = resolution_map or {}
    for story in incomplete:
        action = resolutions.get(story.id, default_action)
        if action == "backlog":
            restore_story_to_backlog(story)
        elif action == "cancel":
            story.status = "cancelled"
        elif action == "complete":
            story.status = "done"
        # "keep" / "next_sprint": no-op
    db.flush()


def handle_incomplete_stories(db: Session, record: ProjectRecord, project: Project) -> None:
    """Al cerrar sprint vía workflow: devuelve historias incompletas al backlog."""
    if record.record_type != "sprint":
        return
    resolve_incomplete_sprint_stories(db, record, str(project.id), default_action="backlog")


def reparent_to_backlog(db: Session, record: ProjectRecord, project: Project) -> None:
    """Story devuelta al backlog: restaura parent original (épica)."""
    scrum_role = (record.extra or {}).get("scrum_role")
    if scrum_role != "story":
        return
    restore_story_to_backlog(record)
    db.flush()


def _rollup_estimacion(db: Session, parent: ProjectRecord, project: Project) -> None:
    children = _children(db, parent.id, str(project.id))
    total = sum(float(c.estimacion or 0) for c in children)
    parent.estimacion = total if total > 0 else None
    db.flush()


def rollup_to_dev_task(db: Session, record: ProjectRecord, project: Project) -> None:
    if not record.parent_id:
        return
    parent = db.query(ProjectRecord).filter(ProjectRecord.id == record.parent_id).first()
    if not parent:
        return
    _rollup_estimacion(db, parent, project)
    scrum_role = (parent.extra or {}).get("scrum_role")
    if scrum_role == "dev":
        rollup_to_story(db, parent, project)


def rollup_to_story(db: Session, record: ProjectRecord, project: Project) -> None:
    if not record.parent_id:
        return
    parent = db.query(ProjectRecord).filter(ProjectRecord.id == record.parent_id).first()
    if not parent:
        return
    _rollup_estimacion(db, parent, project)
    scrum_role = (parent.extra or {}).get("scrum_role")
    if scrum_role == "story" and parent.parent_id:
        epic = db.query(ProjectRecord).filter(ProjectRecord.id == parent.parent_id).first()
        if epic:
            _rollup_estimacion(db, epic, project)


def rollup_to_epic(db: Session, record: ProjectRecord, project: Project) -> None:
    if not record.parent_id:
        return
    parent = db.query(ProjectRecord).filter(ProjectRecord.id == record.parent_id).first()
    if parent:
        _rollup_estimacion(db, parent, project)


_HANDLERS = {
    "sync_parent_feature": sync_parent_feature,
    "sync_parent_milestone": sync_parent_milestone,
    "sync_from_features": sync_from_features,
    "reparent_to_sprint": reparent_to_sprint,
    "reparent_to_backlog": reparent_to_backlog,
    "rollup_to_epic": rollup_to_epic,
    "rollup_to_story": rollup_to_story,
    "rollup_to_dev_task": rollup_to_dev_task,
    "handle_incomplete_stories": handle_incomplete_stories,
}


def apply_side_effects(
    db: Session,
    effect_names: tuple[str, ...],
    record: ProjectRecord,
    project: Project,
) -> None:
    for name in effect_names:
        handler = _HANDLERS.get(name)
        if handler:
            handler(db, record, project)
