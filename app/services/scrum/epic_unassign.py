"""Desasignar épica del sprint — modal H (SCRUM_KANBAN_MOVEMENTS § H)."""
from __future__ import annotations

from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.schemas.sprints import (
    AffectedChildPreview,
    AffectedStoryPreview,
    UnassignEpicsPreviewResponse,
)
from app.services.access import MemberContext
from app.services.scrum.descendants import collect_scrum_descendants
from app.services.scrum.return_children import ChildrenOnReturn, apply_children_on_return
from app.services.scrum.sprint_membership import parent_is_sprint, unassign_epic_from_sprint, unassign_story_from_sprint
from app.services.workflow.engine import apply_transition

OnUnassignStories = Literal["abort_if_pending", "return", "cancel"]


def _sprint_ids(db: Session, project_id: str) -> set[str]:
    sprints = (
        db.query(ProjectRecord.id)
        .filter(
            ProjectRecord.project_id == project_id,
            ProjectRecord.record_type == "sprint",
        )
        .all()
    )
    return {str(s[0]) for s in sprints}


def _story_epic_id(story: ProjectRecord, epic_ids: set[str]) -> str | None:
    extra = story.extra or {}
    original = extra.get("original_parent_id")
    if original and str(original) in epic_ids:
        return str(original)
    if story.parent_id and str(story.parent_id) in epic_ids:
        return str(story.parent_id)
    return None


def stories_in_sprint_for_epics(
    db: Session,
    project_id: str,
    epic_ids: list[str],
) -> list[ProjectRecord]:
    """Historias con parent=sprint y membership épica vía original_parent_id."""
    epic_id_set = {str(e) for e in epic_ids}
    sprint_id_set = _sprint_ids(db, project_id)
    if not sprint_id_set:
        return []

    stories = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.project_id == project_id,
            ProjectRecord.record_type == "task",
        )
        .all()
    )
    result: list[ProjectRecord] = []
    for story in stories:
        if (story.extra or {}).get("scrum_role") != "story":
            continue
        if not parent_is_sprint(db, story.parent_id):
            continue
        epic_id = _story_epic_id(story, epic_id_set)
        if epic_id and epic_id in epic_id_set:
            result.append(story)
    return result


def _child_previews(db: Session, story: ProjectRecord) -> list[AffectedChildPreview]:
    descendants = collect_scrum_descendants(db, story, str(story.project_id))
    return [
        AffectedChildPreview(
            id=str(d.id),
            title=d.title,
            status=d.status,
            scrum_role=str((d.extra or {}).get("scrum_role") or ""),
        )
        for d in descendants
        if (d.extra or {}).get("scrum_role") in ("dev", "subtask")
    ]


def build_unassign_preview(
    db: Session,
    project_id: str,
    epic_ids: list[str],
) -> UnassignEpicsPreviewResponse:
    stories = stories_in_sprint_for_epics(db, project_id, epic_ids)
    story_previews: list[AffectedStoryPreview] = []
    has_blocked = False
    for story in stories:
        is_blocked = story.status == "blocked"
        if is_blocked:
            has_blocked = True
        epic_id = _story_epic_id(story, {str(e) for e in epic_ids}) or ""
        story_previews.append(
            AffectedStoryPreview(
                id=str(story.id),
                title=story.title,
                status=story.status,
                sprint_id=str(story.parent_id or ""),
                epic_id=epic_id,
                is_blocked=is_blocked,
                children=_child_previews(db, story),
            )
        )
    return UnassignEpicsPreviewResponse(
        epic_ids=epic_ids,
        stories=story_previews,
        has_blocked_stories=has_blocked,
        requires_confirmation=len(story_previews) > 0,
    )


def raise_requires_unassign_confirmation(preview: UnassignEpicsPreviewResponse) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "requires_unassign_confirmation",
            "message": "Hay historias en sprint ligadas a la(s) épica(s). Confirma qué hacer con ellas.",
            **preview.model_dump(),
        },
    )


def _children_mode(
    on_unassign_children: Literal["unchanged", "return_to_backlog", "cancel"] | None,
) -> ChildrenOnReturn:
    if on_unassign_children in ("return_to_backlog", "cancel"):
        return on_unassign_children
    return "unchanged"


def _reparent_story_to_epic(story: ProjectRecord) -> None:
    extra = dict(story.extra or {})
    original = extra.pop("original_parent_id", None)
    story.extra = extra
    if original:
        story.parent_id = original


def apply_stories_on_epic_unassign(
    db: Session,
    project: Project,
    stories: list[ProjectRecord],
    on_unassign_stories: OnUnassignStories,
    on_unassign_children: Literal["unchanged", "return_to_backlog", "cancel"] | None,
    actor_id: str,
    member_ctx: MemberContext,
) -> None:
    children_mode = _children_mode(on_unassign_children)
    for story in stories:
        if on_unassign_stories == "return":
            unassign_story_from_sprint(db, story)
            apply_children_on_return(
                db, story, project, children_mode, resolved_by=actor_id,
            )
        elif on_unassign_stories == "cancel":
            apply_transition(db, project, story, "cancelar", actor_id, member_ctx)
            _reparent_story_to_epic(story)
            apply_children_on_return(
                db, story, project, children_mode, resolved_by=actor_id,
            )
    db.flush()


def unassign_epics_from_sprint(
    db: Session,
    project: Project,
    epic_ids: list[str],
    *,
    on_unassign_stories: OnUnassignStories | None,
    on_unassign_children: Literal["unchanged", "return_to_backlog", "cancel"] | None,
    actor_id: str,
    member_ctx: MemberContext,
) -> None:
    """Desasigna épicas; si hay historias en sprint, requiere política explícita."""
    project_id = str(project.id)
    affected = stories_in_sprint_for_epics(db, project_id, epic_ids)

    if affected and on_unassign_stories is None:
        raise_requires_unassign_confirmation(build_unassign_preview(db, project_id, epic_ids))

    if affected and on_unassign_stories == "abort_if_pending":
        return

    if affected and on_unassign_stories in ("return", "cancel"):
        apply_stories_on_epic_unassign(
            db, project, affected, on_unassign_stories, on_unassign_children, actor_id, member_ctx,
        )

    epics = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.id.in_(epic_ids),
            ProjectRecord.project_id == project_id,
        )
        .all()
    )
    for epic in epics:
        if (epic.extra or {}).get("scrum_role") != "epic":
            continue
        unassign_epic_from_sprint(db, epic)
