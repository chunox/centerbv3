"""
Preview y aplicación de transiciones en cascada (Scrum kanban).

Al mover una entidad padre (épica, historia, dev task), el usuario puede
propagar el cambio a todos los descendientes del sprint.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.domain.packs.definitions import TEMPLATE_TO_PACK, TransitionDef
from app.models.entities import Project, ProjectRecord
from app.services.access import MemberContext
from app.services.blockers import has_active_blocker_on_chain, has_unsatisfied_dependencies
from app.services.workflow.engine import (
    WorkflowError,
    _get_transition,
    _resolve_entity_type,
    apply_transition,
)

CascadeMode = Literal["none", "all"]

_SCRUM_ROLE_ENTITY = {
    "epic": "epic",
    "story": "story",
    "dev": "dev_task",
    "subtask": "subtask",
}

_DEPTH = {"story": 0, "dev": 1, "subtask": 2}


@dataclass
class CascadeChildPlan:
    id: str
    title: str
    entity_type: str
    scrum_role: str
    from_status: str
    to_status: str
    action_id: str | None
    can_transition: bool
    is_blocked: bool
    reason: str | None = None


@dataclass
class CascadePreview:
    record_id: str
    title: str
    entity_type: str
    scrum_role: str
    from_status: str
    to_status: str
    action_id: str
    children: list[CascadeChildPlan]
    requires_confirmation: bool


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


def _find_transition_to_target(
    wf_transitions: tuple[TransitionDef, ...],
    current_status: str,
    target_status: str,
) -> TransitionDef | None:
    for t in wf_transitions:
        if current_status in t.from_states and t.to_state == target_status:
            return t
    return None


def _child_plan(
    db: Session,
    child: ProjectRecord,
    pack_key: str,
    settings: dict,
    target_status: str,
) -> CascadeChildPlan:
    entity_type = _resolve_entity_type(child, pack_key)
    scrum_role = (child.extra or {}).get("scrum_role") or entity_type
    from app.domain.packs.definitions import get_pack

    pack = get_pack(pack_key)
    variant_key = (settings or {}).get(f"{entity_type}_workflow")
    variant_full = f"{entity_type}.{variant_key}" if variant_key else ""
    wf = pack.workflow_variants.get(variant_full) if variant_key and pack else None
    if wf is None and pack:
        wf = pack.workflows.get(entity_type)

    if child.status == target_status:
        return CascadeChildPlan(
            id=str(child.id),
            title=child.title,
            entity_type=entity_type,
            scrum_role=str(scrum_role),
            from_status=child.status,
            to_status=target_status,
            action_id=None,
            can_transition=True,
            is_blocked=False,
            reason="already_at_target",
        )

    if not wf or target_status not in wf.states:
        return CascadeChildPlan(
            id=str(child.id),
            title=child.title,
            entity_type=entity_type,
            scrum_role=str(scrum_role),
            from_status=child.status,
            to_status=target_status,
            action_id=None,
            can_transition=False,
            is_blocked=has_active_blocker_on_chain(db, child),
            reason="target_state_not_available",
        )

    transition = _find_transition_to_target(wf.transitions, child.status, target_status)
    is_blocked = has_active_blocker_on_chain(db, child)
    has_deps = has_unsatisfied_dependencies(db, child)

    if not transition:
        return CascadeChildPlan(
            id=str(child.id),
            title=child.title,
            entity_type=entity_type,
            scrum_role=str(scrum_role),
            from_status=child.status,
            to_status=target_status,
            action_id=None,
            can_transition=False,
            is_blocked=is_blocked,
            reason="no_direct_transition",
        )

    reason = None
    can = True
    if is_blocked:
        can = False
        reason = "blocked"
    elif has_deps and "dependency_satisfied" in (transition.gates or ()):
        can = False
        reason = "dependency_unsatisfied"

    return CascadeChildPlan(
        id=str(child.id),
        title=child.title,
        entity_type=entity_type,
        scrum_role=str(scrum_role),
        from_status=child.status,
        to_status=target_status,
        action_id=transition.action_id,
        can_transition=can,
        is_blocked=is_blocked,
        reason=reason,
    )


def preview_cascade_transition(
    db: Session,
    project: Project,
    record: ProjectRecord,
    action_id: str,
) -> CascadePreview:
    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    settings: dict = project.settings or {}
    entity_type = _resolve_entity_type(record, pack_key)
    parent_transition = _get_transition(pack_key, entity_type, action_id, settings)
    target_status = parent_transition.to_state
    scrum_role = (record.extra or {}).get("scrum_role") or entity_type

    descendants = collect_scrum_descendants(db, record, str(project.id))
    children = [
        _child_plan(db, child, pack_key, settings, target_status)
        for child in sorted(
            descendants,
            key=lambda r: _DEPTH.get((r.extra or {}).get("scrum_role", ""), 99),
        )
    ]

    affected = [
        c for c in children
        if c.from_status != target_status and c.reason != "already_at_target"
    ]
    requires_confirmation = len(affected) > 0

    return CascadePreview(
        record_id=str(record.id),
        title=record.title,
        entity_type=entity_type,
        scrum_role=str(scrum_role),
        from_status=record.status,
        to_status=target_status,
        action_id=action_id,
        children=children,
        requires_confirmation=requires_confirmation,
    )


def apply_cascade_transition(
    db: Session,
    project: Project,
    record: ProjectRecord,
    action_id: str,
    actor_id: str,
    member_ctx: MemberContext,
    *,
    cascade: CascadeMode = "none",
    skip_blocked: bool = False,
) -> ProjectRecord:
    preview = preview_cascade_transition(db, project, record, action_id)

    if cascade == "all":
        to_apply = [
            c for c in preview.children
            if c.action_id and c.can_transition and c.from_status != c.to_status
        ]
        blocked = [c for c in preview.children if c.is_blocked and c.from_status != c.to_status]
        if blocked and not skip_blocked:
            raise WorkflowError(
                f"{len(blocked)} entidad(es) hija(s) bloqueada(s). "
                "Usa skip_blocked=true para omitirlas."
            )

    apply_transition(db, project, record, action_id, actor_id, member_ctx)

    if cascade == "all":
        for plan in preview.children:
            if not plan.action_id or plan.from_status == plan.to_status:
                continue
            if not plan.can_transition:
                continue
            if plan.is_blocked and skip_blocked:
                continue
            child = db.query(ProjectRecord).filter(ProjectRecord.id == plan.id).first()
            if child and child.status == plan.from_status:
                apply_transition(db, project, child, plan.action_id, actor_id, member_ctx)

    return record
