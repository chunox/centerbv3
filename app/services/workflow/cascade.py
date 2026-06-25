"""
Preview y aplicación de transiciones en cascada (Scrum kanban).

Al mover una entidad padre (épica, historia, dev task), el usuario puede
propagar el cambio a todos los descendientes del sprint.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from app.domain.packs.definitions import TEMPLATE_TO_PACK, TransitionDef
from app.models.entities import Project, ProjectRecord
from app.services.access import MemberContext
from app.domain.scrum.states import SCRUM_TERMINAL_STATES
from app.services.blockers import has_active_blocker_on_chain, has_blocked_descendant, has_unsatisfied_dependencies
from app.services.scrum.sprint_membership import is_in_product_backlog
from app.services.scrum.descendants import collect_scrum_descendants
from app.services.scrum.epic_invariants import (
    EPIC_DONE_ALIGNED_STORY_STATUSES,
    assert_epic_done_allowed,
    build_epic_done_preview_meta,
    misaligned_stories_for_epic_done,
)
from app.services.workflow.engine import (
    _get_transition,
    _resolve_entity_type,
    apply_transition,
)
from app.services.workflow.errors import WorkflowError

CascadeMode = Literal[
    "none", "all", "movable_only", "movable_and_cancel_rest", "cancel_misaligned_stories",
]

_PIPELINE_RANK = {
    "backlog": 0,
    "to_do": 1,
    "in_progress": 2,
    "in_review": 3,
    "done": 4,
}

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
    epic_done_blocked: bool = False
    stories_misaligned: list[dict] = field(default_factory=list)
    blocked_in_chain: bool = False
    children_ahead: list[CascadeChildPlan] = field(default_factory=list)
    epic_done_misaligned: bool = False
    cascade_modes_available: list[str] = field(default_factory=list)


def resolve_cascade_mode(
    *,
    cascade: str = "none",
    cascade_mode: str = "none",
) -> CascadeMode:
    if cascade_mode != "none":
        return cascade_mode  # type: ignore[return-value]
    if cascade == "all":
        return "all"
    return "none"


def _is_child_ahead_of_target(child_status: str, target_status: str) -> bool:
    if child_status in SCRUM_TERMINAL_STATES or child_status == "blocked":
        return False
    if target_status in SCRUM_TERMINAL_STATES or target_status == "blocked":
        return False
    child_rank = _PIPELINE_RANK.get(child_status)
    target_rank = _PIPELINE_RANK.get(target_status)
    if child_rank is None or target_rank is None:
        return False
    return child_rank > target_rank


def _blocked_in_chain(db: Session, record: ProjectRecord, children: list[CascadeChildPlan]) -> bool:
    if record.status == "blocked":
        return True
    if has_blocked_descendant(db, record):
        return True
    return any(c.is_blocked or c.reason == "blocked" for c in children)


def _is_epic_done_transition(record: ProjectRecord, action_id: str, to_status: str) -> bool:
    return (
        (record.extra or {}).get("scrum_role") == "epic"
        and action_id == "complete"
        and to_status == "done"
    )


def _compute_cascade_modes_available(
    *,
    blocked_in_chain: bool,
    record: ProjectRecord,
    action_id: str,
    to_status: str,
    children: list[CascadeChildPlan],
    epic_done_misaligned: bool,
) -> list[str]:
    if blocked_in_chain:
        return []

    is_epic_done = _is_epic_done_transition(record, action_id, to_status)
    if is_epic_done and epic_done_misaligned:
        return ["all", "cancel_misaligned_stories"]

    needs_moves = [
        c for c in children
        if c.from_status != to_status and c.reason != "already_at_target"
    ]
    if not needs_moves:
        return []

    has_immovable = any(not c.can_transition for c in needs_moves)
    if has_immovable:
        modes = ["movable_only", "movable_and_cancel_rest"]
        if not any(c.reason == "blocked" or c.is_blocked for c in needs_moves):
            modes.insert(0, "all")
        return modes

    if is_epic_done:
        return ["all"]
    return ["all"]


def _find_transition_to_target(
    wf_transitions: tuple[TransitionDef, ...],
    current_status: str,
    target_status: str,
) -> TransitionDef | None:
    path = find_transition_path(wf_transitions, current_status, target_status)
    if not path:
        return None
    return path[0]


def find_transition_path(
    wf_transitions: tuple[TransitionDef, ...],
    from_status: str,
    to_status: str,
) -> list[TransitionDef]:
    """BFS: secuencia mínima de transiciones entre dos estados."""
    if from_status == to_status:
        return []
    from collections import deque

    queue: deque[tuple[str, list[TransitionDef]]] = deque([(from_status, [])])
    visited = {from_status}
    while queue:
        state, path = queue.popleft()
        for t in wf_transitions:
            if state not in t.from_states:
                continue
            next_state = t.to_state
            new_path = path + [t]
            if next_state == to_status:
                return new_path
            if next_state not in visited:
                visited.add(next_state)
                queue.append((next_state, new_path))
    return []


def _child_is_movement_blocked(db: Session, child: ProjectRecord) -> bool:
    if child.status == "blocked":
        return True
    if child.status in ("done", "cancelled"):
        return False
    return has_active_blocker_on_chain(db, child)


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

    if (
        scrum_role == "story"
        and child.status == "backlog"
        and target_status not in SCRUM_TERMINAL_STATES
        and target_status != "blocked"
        and is_in_product_backlog(db, child)
    ):
        return CascadeChildPlan(
            id=str(child.id),
            title=child.title,
            entity_type=entity_type,
            scrum_role=str(scrum_role),
            from_status=child.status,
            to_status=target_status,
            action_id=None,
            can_transition=False,
            is_blocked=False,
            reason="needs_sprint",
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
            is_blocked=_child_is_movement_blocked(db, child),
            reason="target_state_not_available",
        )

    transition = _find_transition_to_target(wf.transitions, child.status, target_status)
    path = find_transition_path(wf.transitions, child.status, target_status) if wf else []
    is_blocked = _child_is_movement_blocked(db, child)
    has_deps = has_unsatisfied_dependencies(db, child)

    if not transition and not path:
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
    elif path:
        for step in path:
            if has_deps and "dependency_satisfied" in (step.gates or ()):
                can = False
                reason = "dependency_unsatisfied"
                break
    elif has_deps and transition and "dependency_satisfied" in (transition.gates or ()):
        can = False
        reason = "dependency_unsatisfied"

    first_action = path[0].action_id if path else (transition.action_id if transition else None)

    return CascadeChildPlan(
        id=str(child.id),
        title=child.title,
        entity_type=entity_type,
        scrum_role=str(scrum_role),
        from_status=child.status,
        to_status=target_status,
        action_id=first_action,
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
    parent_transition = _get_transition(pack_key, entity_type, action_id, settings, record.status)
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

    epic_done_blocked = False
    stories_misaligned: list[dict] = []
    epic_meta = build_epic_done_preview_meta(db, project, record, action_id)
    if epic_meta:
        epic_done_blocked = epic_meta.epic_done_blocked
        stories_misaligned = [
            {"id": s.id, "title": s.title, "status": s.status}
            for s in epic_meta.stories_misaligned
        ]
        if stories_misaligned and not epic_done_blocked:
            requires_confirmation = True

    children_ahead = [
        c for c in children
        if _is_child_ahead_of_target(c.from_status, target_status)
    ]
    if children_ahead:
        requires_confirmation = True

    epic_done_misaligned = len(stories_misaligned) > 0
    blocked_chain = _blocked_in_chain(db, record, children)
    cascade_modes = _compute_cascade_modes_available(
        blocked_in_chain=blocked_chain,
        record=record,
        action_id=action_id,
        to_status=target_status,
        children=children,
        epic_done_misaligned=epic_done_misaligned,
    )

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
        epic_done_blocked=epic_done_blocked,
        stories_misaligned=stories_misaligned,
        blocked_in_chain=blocked_chain,
        children_ahead=children_ahead,
        epic_done_misaligned=epic_done_misaligned,
        cascade_modes_available=cascade_modes,
    )


def _workflow_for_child(
    pack_key: str,
    entity_type: str,
    settings: dict,
):
    from app.domain.packs.definitions import get_pack

    pack = get_pack(pack_key)
    variant_key = (settings or {}).get(f"{entity_type}_workflow")
    variant_full = f"{entity_type}.{variant_key}" if variant_key else ""
    wf = pack.workflow_variants.get(variant_full) if variant_key and pack else None
    if wf is None and pack:
        wf = pack.workflows.get(entity_type)
    return wf


def _cancel_action_for_status(wf, status: str) -> str | None:
    if not wf:
        return None
    for action_id in ("cancel", "cancelar"):
        for t in wf.transitions:
            if t.action_id == action_id and status in t.from_states:
                return action_id
    return None


def _apply_child_path(
    db: Session,
    project: Project,
    child: ProjectRecord,
    plan: CascadeChildPlan,
    actor_id: str,
    member_ctx: MemberContext,
    pack_key: str,
    settings: dict,
) -> None:
    entity_type = _resolve_entity_type(child, pack_key)
    wf = _workflow_for_child(pack_key, entity_type, settings)
    if not wf:
        return
    path = find_transition_path(wf.transitions, child.status, plan.to_status)
    for step in path:
        if child.status == plan.to_status:
            break
        apply_transition(db, project, child, step.action_id, actor_id, member_ctx)
        db.refresh(child)


def cancel_misaligned_stories_for_epic_done(
    db: Session,
    project: Project,
    epic: ProjectRecord,
    actor_id: str,
    member_ctx: MemberContext,
) -> None:
    """Modal épica→done: todas las historias no terminales pasan a cancelled."""
    from app.services.scrum.return_children import apply_children_on_return

    for story in misaligned_stories_for_epic_done(db, epic):
        if story.status in EPIC_DONE_ALIGNED_STORY_STATUSES:
            continue
        apply_transition(db, project, story, "cancelar", actor_id, member_ctx)
        db.refresh(story)
        apply_children_on_return(
            db, story, project, "cancel", resolved_by=actor_id,
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
) -> ProjectRecord:
    preview = preview_cascade_transition(db, project, record, action_id)

    if cascade in ("all", "cancel_misaligned_stories"):
        blocked_moving = [
            c for c in preview.children
            if c.from_status != c.to_status and c.reason == "blocked"
        ]
        if blocked_moving:
            raise WorkflowError(
                f"{len(blocked_moving)} entidad(es) hija(s) bloqueada(s). "
                "Resuelve los bloqueos antes de aplicar la cascada."
            )
    elif cascade == "none":
        assert_epic_done_allowed(db, project, record, action_id)

    if cascade == "cancel_misaligned_stories":
        if not _is_epic_done_transition(record, action_id, preview.to_status):
            raise WorkflowError(
                "cancel_misaligned_stories solo aplica a épica→done con historias no alineadas."
            )
        cancel_misaligned_stories_for_epic_done(
            db, project, record, actor_id, member_ctx,
        )
        apply_transition(db, project, record, action_id, actor_id, member_ctx)
        return record

    apply_transition(db, project, record, action_id, actor_id, member_ctx)

    if cascade == "none":
        return record

    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    settings: dict = project.settings or {}

    for plan in preview.children:
        if plan.from_status == plan.to_status:
            continue
        child = db.query(ProjectRecord).filter(ProjectRecord.id == plan.id).first()
        if not child or child.status != plan.from_status:
            continue

        if cascade == "all":
            if not plan.can_transition:
                continue
            _apply_child_path(db, project, child, plan, actor_id, member_ctx, pack_key, settings)
        elif cascade == "movable_only":
            if not plan.can_transition:
                continue
            _apply_child_path(db, project, child, plan, actor_id, member_ctx, pack_key, settings)
        elif cascade == "movable_and_cancel_rest":
            if plan.can_transition:
                _apply_child_path(db, project, child, plan, actor_id, member_ctx, pack_key, settings)
            elif child.status not in SCRUM_TERMINAL_STATES:
                entity_type = _resolve_entity_type(child, pack_key)
                wf = _workflow_for_child(pack_key, entity_type, settings)
                cancel_action = _cancel_action_for_status(wf, child.status)
                if cancel_action:
                    apply_transition(
                        db, project, child, cancel_action, actor_id, member_ctx,
                    )
                    db.refresh(child)

    return record
