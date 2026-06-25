"""Asignación de sprint y validación de invariantes para épicas e historias."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord
from app.services.workflow.errors import WorkflowError
from app.services.workflow.side_effects import restore_story_to_backlog

from app.domain.scrum.states import SCRUM_PIPELINE_SPRINT_REQUIRED_STATUSES

ACTIVE_SPRINT_STATUSES = SCRUM_PIPELINE_SPRINT_REQUIRED_STATUSES


def parent_is_sprint(db: Session, parent_id: str | None) -> bool:
    if not parent_id:
        return False
    parent = db.query(ProjectRecord).filter(ProjectRecord.id == parent_id).first()
    return parent is not None and parent.record_type == "sprint"


def parent_is_epic(db: Session, parent_id: str | None) -> bool:
    if not parent_id:
        return False
    parent = db.query(ProjectRecord).filter(ProjectRecord.id == parent_id).first()
    return parent is not None and (parent.extra or {}).get("scrum_role") == "epic"


def is_story_in_sprint(story: ProjectRecord, db: Session | None = None) -> bool:
    if db is None:
        return False
    return parent_is_sprint(db, story.parent_id)


def is_epic_in_sprint(epic: ProjectRecord) -> bool:
    return bool((epic.extra or {}).get("sprint_id"))


def get_active_sprint(db: Session, project_id: str) -> ProjectRecord | None:
    return (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.project_id == project_id,
            ProjectRecord.record_type == "sprint",
            ProjectRecord.status == "activo",
        )
        .first()
    )


def get_sprint_or_raise(db: Session, project_id: str, sprint_id: str) -> ProjectRecord:
    sprint = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.id == sprint_id,
            ProjectRecord.project_id == project_id,
            ProjectRecord.record_type == "sprint",
        )
        .first()
    )
    if not sprint:
        raise WorkflowError("Sprint no encontrado")
    return sprint


def assign_story_to_sprint(db: Session, story: ProjectRecord, sprint_id: str, *, bump_status: bool = True) -> None:
    role = (story.extra or {}).get("scrum_role")
    if role != "story":
        raise WorkflowError("Solo historias pueden asignarse a un sprint")
    get_sprint_or_raise(db, str(story.project_id), sprint_id)
    if story.parent_id != sprint_id:
        extra = dict(story.extra or {})
        if story.parent_id and not extra.get("original_parent_id"):
            if not parent_is_sprint(db, story.parent_id):
                extra["original_parent_id"] = story.parent_id
        story.extra = extra
        story.parent_id = sprint_id
    if bump_status and story.status == "backlog":
        story.status = "to_do"
    db.flush()


def unassign_story_from_sprint(db: Session, story: ProjectRecord) -> None:
    restore_story_to_backlog(story, db)
    db.flush()


def assign_epic_to_sprint(db: Session, epic: ProjectRecord, sprint_id: str, *, bump_status: bool = True) -> None:
    role = (epic.extra or {}).get("scrum_role")
    if role != "epic":
        raise WorkflowError("Solo épicas pueden asignarse a un sprint")
    get_sprint_or_raise(db, str(epic.project_id), sprint_id)
    extra = dict(epic.extra or {})
    extra["sprint_id"] = sprint_id
    epic.extra = extra
    if bump_status and epic.status == "backlog":
        epic.status = "to_do"
    db.flush()


def unassign_epic_from_sprint(db: Session, epic: ProjectRecord) -> None:
    extra = dict(epic.extra or {})
    extra.pop("sprint_id", None)
    epic.extra = extra
    if epic.status != "blocked":
        epic.status = "backlog"
    db.flush()


def assert_scrum_invariants(db: Session, record: ProjectRecord) -> None:
    role = (record.extra or {}).get("scrum_role")
    if role == "story":
        in_sprint = parent_is_sprint(db, record.parent_id)
        if record.status == "backlog" and in_sprint:
            raise WorkflowError("Historia en backlog no puede tener parent sprint")
        if record.status in ACTIVE_SPRINT_STATUSES and not in_sprint:
            raise WorkflowError("Historia activa debe estar bajo un sprint")
        # status=blocked: válido bajo sprint o bajo épica (product backlog)
    elif role == "epic":
        has_sprint = is_epic_in_sprint(record)
        if record.status == "backlog" and has_sprint:
            raise WorkflowError("Épica en backlog no puede tener sprint asignado")
        if record.status in ACTIVE_SPRINT_STATUSES and not has_sprint:
            raise WorkflowError("Épica activa debe tener sprint asignado")
        # status=blocked: válido con o sin sprint_id


def story_sprint_id(db: Session, story: ProjectRecord) -> str | None:
    if parent_is_sprint(db, story.parent_id):
        return str(story.parent_id) if story.parent_id else None
    return None


def record_sprint_id(db: Session, record: ProjectRecord) -> str | None:
    role = (record.extra or {}).get("scrum_role")
    if role == "story":
        return story_sprint_id(db, record)
    if role == "epic":
        sid = (record.extra or {}).get("sprint_id")
        return str(sid) if sid else None
    return None


def is_in_product_backlog(db: Session, record: ProjectRecord) -> bool:
    role = (record.extra or {}).get("scrum_role")
    if role == "story":
        return parent_is_epic(db, record.parent_id)
    if role == "epic":
        return not is_epic_in_sprint(record)
    return False


def transition_needs_sprint_assignment(
    db: Session,
    record: ProjectRecord,
    gates: tuple[str, ...],
) -> bool:
    if "sprint_assigned" not in gates:
        return False
    role = (record.extra or {}).get("scrum_role")
    if role == "story":
        return not parent_is_sprint(db, record.parent_id)
    if role == "epic":
        return not is_epic_in_sprint(record)
    return False


def apply_sprint_for_transition(
    db: Session,
    record: ProjectRecord,
    sprint_id: str,
) -> None:
    role = (record.extra or {}).get("scrum_role")
    if role == "story":
        assign_story_to_sprint(db, record, sprint_id, bump_status=False)
    elif role == "epic":
        assign_epic_to_sprint(db, record, sprint_id, bump_status=False)
