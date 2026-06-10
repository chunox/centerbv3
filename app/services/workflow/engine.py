"""Motor de transiciones de workflow."""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Feature, FeatureReport, Milestone, Project, Task
from app.services.audit import record_audit_log
from app.services.features import cancel_feature_cascade
from app.services.workflow.authorize import assert_any_capability
from app.services.workflow.gates import check_transition_conditions, evaluate_gates
from app.services.workflow.store import get_active_workflow
from app.services.workflow.capabilities import users_with_capability
from app.services.notifications import create_notification


def _find_transition(
    workflow: dict[str, Any],
    action_id: str,
    current_state: str,
    *,
    project: Project | None = None,
) -> dict[str, Any] | None:
    for t in workflow.get("transitions", []):
        if t.get("id") != action_id:
            continue
        from_states = t.get("from", [])
        if current_state not in from_states and "*" not in from_states:
            continue
        if project is not None and not check_transition_conditions(
            project, t.get("conditions")
        ):
            continue
        return t
    return None


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
    workflow = get_active_workflow(db, project.id, entity_type)
    if workflow is None:
        raise HTTPException(status_code=500, detail=f"Workflow '{entity_type}' no configurado")

    current = getattr(entity, "estado", None)
    if current is None:
        raise HTTPException(status_code=409, detail="Entidad sin estado")

    transition = _find_transition(workflow, action_id, current, project=project)
    if transition is None:
        raise HTTPException(
            status_code=409,
            detail=f"Transición '{action_id}' no permitida desde '{current}'",
        )

    required = transition.get("required_capabilities", [])
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

    entidad_tipo_map = {
        "feature": "feature",
        "task": "tarea",
        "query": "feature_query",
        "report": "feature_report",
    }
    entidad_tipo = entidad_tipo_map.get(entity_type, entity_type)
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

    _run_side_effects(
        db,
        project=project,
        entity=entity,
        entity_type=entity_type,
        action_id=action_id,
        actor_user_id=actor_user_id,
        effects=transition.get("side_effects", []),
        form_data=form_data,
        side_effect_context=side_effect_context,
    )
    return nuevo


def _notification_entidad_tipo(entity_type: str) -> str:
    return {
        "feature": "feature",
        "task": "tarea",
        "query": "feature_query",
        "report": "feature_report",
        "milestone": "milestone",
    }.get(entity_type, entity_type)


def _run_side_effects(
    db: Session,
    *,
    project: Project,
    entity: Any,
    entity_type: str,
    action_id: str,
    actor_user_id: uuid.UUID,
    effects: list[dict[str, Any]],
    form_data: dict[str, Any] | None = None,
    side_effect_context: dict[str, Any] | None = None,
) -> None:
    ctx = side_effect_context or {}
    entidad_tipo = _notification_entidad_tipo(entity_type)
    for effect in effects:
        etype = effect.get("type")
        if etype == "notify":
            cap = effect.get("target", {}).get("capability")
            if cap:
                for uid in users_with_capability(db, project.id, cap):
                    create_notification(
                        db,
                        user_id=uid,
                        project_id=project.id,
                        tipo="estado_changed",
                        entidad_tipo=entidad_tipo,  # type: ignore[arg-type]
                        entidad_id=entity.id,
                    )
        elif etype == "notify_reporter" and entity_type == "report" and isinstance(
            entity, FeatureReport
        ):
            create_notification(
                db,
                user_id=entity.reported_by,
                project_id=project.id,
                tipo=effect.get("notification_tipo", "reporte_resuelto"),
                entidad_tipo="feature_report",
                entidad_id=entity.id,
            )
        elif etype == "generate_feature_from_report" and entity_type == "report" and isinstance(
            entity, FeatureReport
        ):
            from app.services.feature_reports import generate_feature_from_report

            milestone_id = ctx.get("milestone_id")
            if milestone_id is None:
                raise HTTPException(
                    status_code=500,
                    detail="milestone_id requerido para generate_feature_from_report",
                )
            milestone = db.get(Milestone, milestone_id)
            if milestone is None:
                raise HTTPException(status_code=404, detail="Hito no encontrado")
            original = db.get(Feature, entity.feature_id)
            if original is None:
                raise HTTPException(status_code=404, detail="Feature original no encontrada")
            generate_feature_from_report(
                db,
                entity,
                original,
                project,
                milestone,
                actor_user_id=actor_user_id,
                form_data=form_data or ctx.get("form_data"),
            )
        elif etype == "sync_milestone_from_report" and entity_type == "report":
            milestone_id = ctx.get("milestone_id")
            if milestone_id is not None:
                milestone = db.get(Milestone, milestone_id)
                if milestone is not None:
                    from app.services.milestones import sync_milestone_state

                    sync_milestone_state(
                        db, milestone, project, actor_user_id=actor_user_id
                    )
        elif etype == "cancel_features_cascade" and entity_type == "milestone" and isinstance(
            entity, Milestone
        ):
            from sqlalchemy import select

            features = list(
                db.scalars(select(Feature).where(Feature.milestone_id == entity.id))
            )
            for feature in features:
                if feature.estado != "cancelado":
                    cancel_feature_cascade(
                        db, feature, project, actor_user_id=actor_user_id
                    )
        elif etype == "cancel_tasks_cascade" and entity_type == "feature":
            cancel_feature_cascade(db, entity, project, actor_user_id=actor_user_id)
        elif etype == "sync_tasks" and entity_type == "feature":
            rule = effect.get("rule")
            if rule == "complete_ready_for_test":
                from app.services.features import load_active_tasks

                tasks = load_active_tasks(db, entity.id)
                for task in tasks:
                    if task.estado == "ready_for_test":
                        prev = task.estado
                        task.estado = "completed"
                        record_audit_log(
                            db,
                            project_id=project.id,
                            user_id=actor_user_id,
                            entidad_tipo="tarea",
                            entidad_id=task.id,
                            accion="estado_changed",
                            campo="estado",
                            valor_anterior=prev,
                            valor_nuevo="completed (workflow)",
                        )
        elif etype == "rework_tasks" and entity_type == "feature":
            from app.services.features import load_active_tasks

            tasks = load_active_tasks(db, entity.id)
            for task in tasks:
                if task.estado == "ready_for_test":
                    prev = task.estado
                    task.estado = "in_progress"
                    record_audit_log(
                        db,
                        project_id=project.id,
                        user_id=actor_user_id,
                        entidad_tipo="tarea",
                        entidad_id=task.id,
                        accion="estado_changed",
                        campo="estado",
                        valor_anterior=prev,
                        valor_nuevo="in_progress (workflow_rework)",
                    )


def get_available_transitions(
    db: Session,
    project: Project,
    entity: Any,
    *,
    entity_type: str,
    user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    from app.services.workflow.capabilities import get_effective_capabilities

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
        if not check_transition_conditions(project, t.get("conditions")):
            continue
        required = t.get("required_capabilities", [])
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
