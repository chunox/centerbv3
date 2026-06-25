"""Helpers para transiciones Scrum con asignación de sprint."""
from __future__ import annotations

from fastapi import HTTPException, status

from app.domain.packs.definitions import TEMPLATE_TO_PACK
from app.models.entities import Project, ProjectRecord
from app.services.scrum.sprint_membership import (
    apply_sprint_for_transition,
    get_active_sprint,
    transition_needs_sprint_assignment,
)
from app.services.workflow.engine import _get_transition, _resolve_entity_type


def active_sprint_id(db, project_id: str) -> str | None:
    sprint = get_active_sprint(db, project_id)
    return str(sprint.id) if sprint else None


def get_transition_for_record(
    project: Project,
    record: ProjectRecord,
    action_id: str,
):
    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    settings: dict = project.settings or {}
    entity_type = _resolve_entity_type(record, pack_key)
    transition = _get_transition(pack_key, entity_type, action_id, settings, record.status)
    return pack_key, entity_type, transition


def ensure_sprint_for_transition(
    db,
    project: Project,
    record: ProjectRecord,
    action_id: str,
    sprint_id: str | None,
) -> tuple[bool, str | None]:
    """
    Si la transición requiere sprint y viene sprint_id, asigna antes.
    Retorna (needs_sprint_assignment, active_sprint_id).
    """
    _, _, transition = get_transition_for_record(project, record, action_id)
    needs = transition_needs_sprint_assignment(db, record, transition.gates)
    active_id = active_sprint_id(db, str(project.id))
    if needs:
        if sprint_id:
            apply_sprint_for_transition(db, record, sprint_id)
            return False, active_id
        return True, active_id
    return False, active_id


def raise_requires_sprint_assignment(record: ProjectRecord, active_sprint_id: str | None) -> None:
    role = (record.extra or {}).get("scrum_role", "")
    label = "historia" if role == "story" else "épica"
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "requires_sprint_assignment",
            "message": f"La {label} no tiene sprint asignado",
            "record_id": str(record.id),
            "active_sprint_id": active_sprint_id,
        },
    )
