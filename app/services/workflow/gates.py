"""Plugins de gates para transiciones de workflow."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Feature, FeatureReport, Project, Task
from app.services.features import load_active_tasks, uat_gate_status


def evaluate_gates(
    db: Session,
    *,
    gate_specs: list[dict[str, Any]],
    project: Project,
    entity: Any,
    entity_type: str,
) -> None:
    for spec in gate_specs:
        gate_type = spec.get("type")
        if gate_type == "uat_tasks_complete":
            if entity_type != "feature" or not isinstance(entity, Feature):
                continue
            tasks = load_active_tasks(db, entity.id)
            gate = uat_gate_status(entity, tasks)
            if not gate["can_pass_to_uat"]:
                raise HTTPException(
                    status_code=409,
                    detail={"message": "Gate UAT no cumplido", **gate},
                )
        elif gate_type == "blocked_by_active_query":
            if getattr(entity, "bloqueada", False):
                raise HTTPException(
                    status_code=409,
                    detail="La entidad está bloqueada por consultas activas",
                )
        elif gate_type == "project_active":
            if project.estado != "activo":
                raise HTTPException(
                    status_code=409,
                    detail="El proyecto no está activo",
                )
        elif gate_type == "report_source_feature_complete":
            if entity_type != "report" or not isinstance(entity, FeatureReport):
                continue
            source = db.get(Feature, entity.feature_id)
            if source is None or source.estado != "completado":
                raise HTTPException(
                    status_code=409,
                    detail="La feature original debe estar en completado",
                )


def check_transition_conditions(
    project: Project,
    conditions: list[dict[str, Any]] | None,
) -> bool:
    if not conditions:
        return True
    for cond in conditions:
        if cond.get("type") == "project_tipo":
            allowed = cond.get("in", [])
            if project.tipo not in allowed:
                return False
    return True
