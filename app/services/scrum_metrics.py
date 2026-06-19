"""Métricas Scrum: velocity y sincronización de sprint (horas)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord
from app.services.scrum_effort import batch_feature_effort_hours, get_feature_sprint_id
from app.services.scrum_structure import list_features_for_sprint


def compute_sprint_completed_horas(
    db: Session, project_id: uuid.UUID, sprint_id: uuid.UUID
) -> float:
    features = [
        f
        for f in list_features_for_sprint(db, project_id, sprint_id)
        if f.estado == "completado"
    ]
    if not features:
        return 0.0
    effort = batch_feature_effort_hours(db, project_id, [f.id for f in features])
    return sum(effort.values())


def sync_sprint_horas_completadas(
    db: Session,
    sprint: ProjectRecord,
    *,
    commit: bool = True,
) -> float:
    """Calcula horas completadas del sprint y persiste en milestone.data."""
    total = compute_sprint_completed_horas(db, sprint.project_id, sprint.id)
    data = dict(sprint.data or {})
    data["horas_completadas"] = total
    sprint.data = data
    if commit:
        db.commit()
        db.refresh(sprint)
    return total


def list_sprint_velocity(
    db: Session,
    project_id: uuid.UUID,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    from app.services.scrum_v2_structure import is_sprint_record

    sprints = list(
        db.scalars(
            select(ProjectRecord)
            .where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type.in_(("sprint", "milestone")),
            )
            .order_by(ProjectRecord.orden.asc(), ProjectRecord.created_at.asc())
        )
    )
    completed = [s for s in sprints if s.estado == "completado" and is_sprint_record(s)]
    tail = completed[-limit:] if len(completed) > limit else completed
    out: list[dict[str, Any]] = []
    for s in tail:
        data = s.data or {}
        out.append(
            {
                "sprint_id": str(s.id),
                "titulo": s.titulo,
                "horas_planeadas": data.get("horas_planeadas"),
                "horas_completadas": data.get("horas_completadas"),
                "predictibilidad_pct": _predictibilidad_pct(
                    data.get("horas_planeadas"),
                    data.get("horas_completadas"),
                ),
                "sprint_goal": data.get("sprint_goal"),
                "fecha_fin": s.fecha_fin.isoformat() if s.fecha_fin else None,
            }
        )
    return out


def _predictibilidad_pct(horas_planeadas: Any, horas_completadas: Any) -> float | None:
    try:
        planned = float(horas_planeadas)
    except (TypeError, ValueError):
        return None
    try:
        completed = float(horas_completadas)
    except (TypeError, ValueError):
        return None
    if planned <= 0:
        return None
    return round((completed / planned) * 100, 1)


def sum_sprint_committed_horas(
    db: Session, project_id: uuid.UUID, sprint_id: uuid.UUID
) -> float:
    features = list_features_for_sprint(db, project_id, sprint_id)
    if not features:
        return 0.0
    effort = batch_feature_effort_hours(db, project_id, [f.id for f in features])
    return sum(effort.values())


def sync_sprint_horas_planeadas(
    db: Session,
    sprint: ProjectRecord,
    *,
    commit: bool = True,
) -> float:
    """Recalcula horas comprometidas del sprint y persiste en milestone.data."""
    total = sum_sprint_committed_horas(db, sprint.project_id, sprint.id)
    data = dict(sprint.data or {})
    data["horas_planeadas"] = total
    sprint.data = data
    if commit:
        db.commit()
        db.refresh(sprint)
    return total
