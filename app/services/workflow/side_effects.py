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


def restore_story_to_backlog(story: ProjectRecord, db: Session | None = None) -> None:
    """Devuelve una historia al backlog de su épica y limpia el vínculo al sprint."""
    from app.services.blockers import has_active_blocker_on_chain

    extra = dict(story.extra or {})
    original_epic = extra.pop("original_parent_id", None)
    story.extra = extra
    if original_epic:
        story.parent_id = original_epic
    if db is not None and has_active_blocker_on_chain(db, story):
        story.status = "blocked"
    else:
        story.status = "backlog"


def reparent_to_sprint(db: Session, record: ProjectRecord, project: Project) -> None:
    """Story comprometida: parent_id → sprint activo."""
    from app.services.scrum.sprint_membership import assign_story_to_sprint, get_active_sprint

    scrum_role = (record.extra or {}).get("scrum_role")
    if scrum_role != "story":
        return
    active_sprint = get_active_sprint(db, str(project.id))
    if not active_sprint:
        return
    assign_story_to_sprint(db, record, str(active_sprint.id))


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
            restore_story_to_backlog(story, db)
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
    from app.services.scrum.sprint_membership import unassign_story_from_sprint

    scrum_role = (record.extra or {}).get("scrum_role")
    if scrum_role != "story":
        return
    unassign_story_from_sprint(db, record)


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


def _scrub_block_extra(record: ProjectRecord) -> None:
    from app.domain.scrum.states import EXTRA_BLOCKED_BY_INHERITANCE, EXTRA_STATUS_BEFORE_BLOCK

    extra = dict(record.extra or {})
    extra.pop(EXTRA_STATUS_BEFORE_BLOCK, None)
    extra.pop(EXTRA_BLOCKED_BY_INHERITANCE, None)
    record.extra = extra


def clear_blockers_on_cancel(db: Session, record: ProjectRecord, project: Project) -> None:
    """Resuelve blockers activos al cancelar (SCRUM_KANBAN_MOVEMENTS § cancel)."""
    from app.services.blockers import clear_blockers_on_record

    clear_blockers_on_record(db, str(record.id))
    _scrub_block_extra(record)
    db.flush()


def cancel_all_descendants(
    db: Session,
    record: ProjectRecord,
    project: Project,
    *,
    resolved_by: str | None = None,
) -> None:
    """Cascada cancel_children=all: descendientes → cancelled + limpiar blockers."""
    from app.services.blockers import clear_blockers_on_record
    from app.services.scrum.descendants import collect_scrum_descendants

    role = (record.extra or {}).get("scrum_role")
    if role in ("epic", "story", "dev"):
        descendants = collect_scrum_descendants(db, record, str(project.id))
    else:
        queue = [str(record.id)]
        seen: set[str] = set()
        descendants = []
        while queue:
            pid = queue.pop(0)
            if pid in seen:
                continue
            seen.add(pid)
            for child in _children(db, pid, str(project.id)):
                descendants.append(child)
                queue.append(str(child.id))

    for desc in descendants:
        if desc.status == "cancelled":
            continue
        desc.status = "cancelled"
        clear_blockers_on_record(db, str(desc.id), resolved_by=resolved_by)
        _scrub_block_extra(desc)
    if descendants:
        db.flush()


def reopen_direct_done_children(db: Session, record: ProjectRecord, project: Project) -> None:
    """Hijos directos en done → in_review (un paso). Cascada opcional al reabrir padre."""
    from app.services.scrum.descendants import stories_for_epic

    role = (record.extra or {}).get("scrum_role")
    targets: list[ProjectRecord] = []
    if role == "epic":
        targets = [s for s in stories_for_epic(db, record) if s.status == "done"]
    elif role == "story":
        targets = [
            c for c in _children(db, str(record.id), str(project.id))
            if (c.extra or {}).get("scrum_role") == "dev" and c.status == "done"
        ]
    elif role == "dev":
        targets = [
            c for c in _children(db, str(record.id), str(project.id))
            if (c.extra or {}).get("scrum_role") == "subtask" and c.status == "done"
        ]
    for child in targets:
        child.status = "in_review"
    if targets:
        db.flush()


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
    "clear_blockers_on_cancel": clear_blockers_on_cancel,
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
