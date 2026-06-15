"""Motor de transiciones de workflow."""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.records.types import RecordRef
from app.models.entities import Project, ProjectRecord
from app.services.audit import record_audit_log
from app.services.records.registry import registry
from app.services.workflow.authorize import assert_any_capability, resolve_capability_keys
from app.services.workflow.gates import check_transition_conditions, evaluate_gates
from app.services.workflow.side_effects import run_side_effect
from app.services.workflow.store import get_active_workflow
from app.services.workflow.capabilities import (
    get_effective_capabilities,
    get_user_role_assignments,
)


def _is_dynamic_target_transition(transition: dict[str, Any]) -> bool:
    return bool(transition.get("dynamic_to")) or transition.get("to") == "*"


def normalize_task_workflow_moves(defn: dict[str, Any]) -> dict[str, Any]:
    """Quita move dinámico legacy cuando hay aristas explícitas (grafo kanban)."""
    transitions = list(defn.get("transitions") or [])
    explicit_moves = [
        t
        for t in transitions
        if t.get("id") == "move"
        and not _is_dynamic_target_transition(t)
        and t.get("to")
    ]
    if not explicit_moves:
        return defn
    filtered = [
        t
        for t in transitions
        if not (t.get("id") == "move" and _is_dynamic_target_transition(t))
    ]
    if len(filtered) == len(transitions):
        return defn
    return {**defn, "transitions": filtered}


def _is_explicit_move_transition(transition: dict[str, Any]) -> bool:
    return (
        transition.get("id") == "move"
        and not _is_dynamic_target_transition(transition)
        and bool(transition.get("to"))
    )


def _actor_allowed_for_transition(
    db: Session | None,
    project: Project | None,
    user_id: uuid.UUID | None,
    transition: dict[str, Any],
) -> bool:
    if "allowed_role_slugs" in transition:
        allowed = transition.get("allowed_role_slugs") or []
        if not allowed:
            return False
    elif _is_explicit_move_transition(transition):
        return False
    else:
        return True

    if db is None or project is None or user_id is None:
        return True
    roles = get_user_role_assignments(db, project.id, user_id)
    user_slugs = {r.slug for r in roles}
    return bool(user_slugs.intersection(set(transition.get("allowed_role_slugs") or [])))


def _find_transition(
    workflow: dict[str, Any],
    action_id: str,
    current_state: str,
    *,
    db: Session | None = None,
    project: Project | None = None,
    target_state: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for t in workflow.get("transitions", []):
        if t.get("id") != action_id:
            continue
        from_states = t.get("from", [])
        if current_state not in from_states and "*" not in from_states:
            continue
        if project is not None and not check_transition_conditions(
            db, project, t.get("conditions")
        ):
            continue
        if not _actor_allowed_for_transition(db, project, actor_user_id, t):
            continue
        matches.append(t)

    if not matches:
        return None

    if target_state:
        for t in matches:
            if _is_dynamic_target_transition(t):
                continue
            if t.get("to") == target_state:
                return t
        for t in matches:
            if _is_dynamic_target_transition(t):
                return t
        return None

    return matches[0]


def _state_meta(workflow: dict[str, Any], state_key: str) -> dict[str, Any]:
    for s in workflow.get("states", []):
        if s.get("key") == state_key:
            return s
    return {"key": state_key, "label": state_key, "category": "active", "badge": "info"}


def validate_transition_form_fields(
    transition: dict[str, Any],
    form_data: dict[str, Any] | None,
) -> None:
    fields = transition.get("form_fields") or []
    if not fields:
        return
    data = form_data or {}
    for spec in fields:
        field_id = spec.get("id")
        if not field_id:
            continue
        required = bool(spec.get("required"))
        value = data.get(field_id)
        if required and (
            value is None or (isinstance(value, str) and not value.strip())
        ):
            label = spec.get("label") or field_id
            raise HTTPException(
                status_code=422,
                detail=f"Campo requerido: {label}",
            )


def apply_record_transition(
    db: Session,
    project: Project,
    entity: Any,
    *,
    record_ref: RecordRef,
    action_id: str,
    actor_user_id: uuid.UUID,
    target_state: str | None = None,
    form_data: dict[str, Any] | None = None,
    side_effect_context: dict[str, Any] | None = None,
) -> str:
    entity_type = record_ref.record_type
    workflow = get_active_workflow(db, project.id, entity_type)
    if workflow is None:
        raise HTTPException(status_code=500, detail=f"Workflow '{entity_type}' no configurado")

    current = getattr(entity, "estado", None)
    if current is None:
        raise HTTPException(status_code=409, detail="Entidad sin estado")

    transition = _find_transition(
        workflow,
        action_id,
        current,
        db=db,
        project=project,
        target_state=target_state,
        actor_user_id=actor_user_id,
    )
    if transition is None:
        raise HTTPException(
            status_code=409,
            detail=f"Transición '{action_id}' no permitida desde '{current}'",
        )

    required = resolve_capability_keys(transition.get("required_capabilities", []))
    if required:
        assert_any_capability(db, project.id, actor_user_id, required)

    validate_transition_form_fields(transition, form_data)

    evaluate_gates(
        db,
        gate_specs=transition.get("gates", []),
        project=project,
        entity=entity,
        entity_type=entity_type,
    )

    if transition.get("dynamic_to") and target_state:
        nuevo = target_state
    else:
        nuevo = transition.get("to")
    if nuevo == "*":
        if not target_state:
            raise HTTPException(status_code=422, detail="Se requiere estado destino")
        nuevo = target_state

    if nuevo is None:
        raise HTTPException(status_code=500, detail="Transición sin estado destino")

    valid_states = {s["key"] for s in workflow.get("states", [])}
    if nuevo not in valid_states:
        raise HTTPException(status_code=409, detail=f"Estado '{nuevo}' no válido en workflow")

    anterior = current
    entity.estado = nuevo

    entidad_tipo = registry.audit_entidad_tipo(entity_type)
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo=entidad_tipo,
        entidad_id=entity.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior=anterior,
        valor_nuevo=f"{nuevo} ({action_id})",
    )
    if form_data:
        record_audit_log(
            db,
            project_id=project.id,
            user_id=actor_user_id,
            entidad_tipo=entidad_tipo,
            entidad_id=entity.id,
            accion="estado_changed",
            campo="workflow_form_data",
            valor_nuevo=json.dumps(form_data, ensure_ascii=False),
        )

    for effect in transition.get("side_effects", []):
        run_side_effect(
            db,
            project=project,
            entity=entity,
            entity_type=entity_type,
            action_id=action_id,
            actor_user_id=actor_user_id,
            effect=effect,
            form_data=form_data,
            side_effect_context=side_effect_context,
            entidad_tipo=entidad_tipo,
        )

    if isinstance(entity, ProjectRecord):
        from app.services.communication.engine import (
            dispatch_state_entered_rules,
            dispatch_transition_rules,
        )

        dispatch_transition_rules(
            db,
            project=project,
            actor_user_id=actor_user_id,
            record=entity,
            action_id=action_id,
            from_state=anterior,
            to_state=nuevo,
        )
        dispatch_state_entered_rules(
            db,
            project=project,
            actor_user_id=actor_user_id,
            record=entity,
            from_state=anterior,
            to_state=nuevo,
        )

    return nuevo


def apply_entity_transition(
    db: Session,
    project: Project,
    entity: Any,
    *,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    target_state: str | None = None,
    form_data: dict[str, Any] | None = None,
    side_effect_context: dict[str, Any] | None = None,
) -> str:
    ref = registry.resolve_ref(db, entity_type, entity.id)
    if ref is None:
        ref = RecordRef(
            id=entity.id,
            record_type=entity_type,
            project_id=project.id,
        )
    return apply_record_transition(
        db,
        project,
        entity,
        record_ref=ref,
        action_id=action_id,
        actor_user_id=actor_user_id,
        target_state=target_state,
        form_data=form_data,
        side_effect_context=side_effect_context,
    )


def get_available_transitions(
    db: Session,
    project: Project,
    entity: Any,
    *,
    entity_type: str,
    user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    workflow = get_active_workflow(db, project.id, entity_type)
    if workflow is None:
        return []
    current = getattr(entity, "estado", "")
    caps = get_effective_capabilities(db, project.id, user_id)
    available: list[dict[str, Any]] = []
    for t in workflow.get("transitions", []):
        from_states = t.get("from", [])
        if current not in from_states and "*" not in from_states:
            continue
        if not check_transition_conditions(db, project, t.get("conditions")):
            continue
        if not _actor_allowed_for_transition(db, project, user_id, t):
            continue
        required = resolve_capability_keys(t.get("required_capabilities", []))
        if required and not any(r in caps for r in required):
            continue
        available.append(
            {
                "id": t["id"],
                "label": t.get("label", t["id"]),
                "to": t.get("to"),
                "required_capabilities": required,
            }
        )
    return available


def workflow_state_label(
    db: Session, project_id: uuid.UUID, entity_type: str, state_key: str
) -> str:
    wf = get_active_workflow(db, project_id, entity_type)
    if not wf:
        return state_key
    return _state_meta(wf, state_key).get("label", state_key)
