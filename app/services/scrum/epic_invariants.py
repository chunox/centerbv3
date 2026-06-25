"""Invariantes de cierre de épica (SCRUM_KANBAN_MOVEMENTS § invariante épica done)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.packs.definitions import TEMPLATE_TO_PACK
from app.models.entities import Project, ProjectRecord
from app.services.blockers import has_blocked_descendant
from app.services.scrum.descendants import stories_for_epic
from app.services.workflow.engine import _get_transition, _resolve_entity_type
from app.services.workflow.errors import WorkflowError

EPIC_DONE_ALIGNED_STORY_STATUSES = frozenset({"done", "cancelled"})


@dataclass
class MisalignedStory:
    id: str
    title: str
    status: str


@dataclass
class EpicDonePreviewMeta:
    epic_done_blocked: bool
    stories_misaligned: list[MisalignedStory]


def misaligned_stories_for_epic_done(db: Session, epic: ProjectRecord) -> list[ProjectRecord]:
    return [
        s for s in stories_for_epic(db, epic)
        if s.status not in EPIC_DONE_ALIGNED_STORY_STATUSES
    ]


def epic_done_is_blocked(db: Session, epic: ProjectRecord) -> bool:
    if epic.status == "blocked":
        return True
    return has_blocked_descendant(db, epic)


def build_epic_done_preview_meta(
    db: Session,
    project: Project,
    epic: ProjectRecord,
    action_id: str,
) -> EpicDonePreviewMeta | None:
    if (epic.extra or {}).get("scrum_role") != "epic" or action_id != "complete":
        return None
    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    entity_type = _resolve_entity_type(epic, pack_key)
    transition = _get_transition(pack_key, entity_type, action_id, project.settings or {}, epic.status)
    if transition.to_state != "done":
        return None
    misaligned = misaligned_stories_for_epic_done(db, epic)
    return EpicDonePreviewMeta(
        epic_done_blocked=epic_done_is_blocked(db, epic),
        stories_misaligned=[
            MisalignedStory(id=str(s.id), title=s.title, status=s.status)
            for s in misaligned
        ],
    )


def assert_epic_done_allowed(db: Session, project: Project, epic: ProjectRecord, action_id: str) -> None:
    """Bloquea épica→done si hay historias no terminales (sin cascada all)."""
    meta = build_epic_done_preview_meta(db, project, epic, action_id)
    if meta is None:
        return
    if meta.epic_done_blocked:
        raise WorkflowError(
            "No se puede completar la épica: hay bloqueos activos en la épica o sus descendientes."
        )
    if meta.stories_misaligned:
        ids = ", ".join(s.id for s in meta.stories_misaligned)
        raise WorkflowError(
            f"No se puede completar la épica: {len(meta.stories_misaligned)} historia(s) "
            f"no están en done o cancelled ({ids}). "
            "Usa cascade_mode all o cancel_misaligned_stories."
        )
