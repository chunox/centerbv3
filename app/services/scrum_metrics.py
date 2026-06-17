"""Métricas Scrum: velocity y sincronización de sprint."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord


def _sp_value(sp_str: str | None) -> int:
    if sp_str is None or sp_str == "?":
        return 0
    try:
        return int(sp_str)
    except (ValueError, TypeError):
        return 0


def compute_sprint_completed_sp(db: Session, project_id: uuid.UUID, sprint_id: uuid.UUID) -> int:
    features = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.parent_id == sprint_id,
                ProjectRecord.record_type == "feature",
                ProjectRecord.estado == "completado",
            )
        )
    )
    return sum(_sp_value((f.data or {}).get("story_points")) for f in features)


def sync_sprint_velocidad_real(
    db: Session,
    sprint: ProjectRecord,
    *,
    commit: bool = True,
) -> int:
    """Calcula SP completados del sprint y persiste en milestone.data.velocidad_real."""
    total = compute_sprint_completed_sp(db, sprint.project_id, sprint.id)
    data = dict(sprint.data or {})
    data["velocidad_real"] = total
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
    sprints = list(
        db.scalars(
            select(ProjectRecord)
            .where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "milestone",
            )
            .order_by(ProjectRecord.orden.asc(), ProjectRecord.created_at.asc())
        )
    )
    completed = [s for s in sprints if s.estado == "completado"]
    tail = completed[-limit:] if len(completed) > limit else completed
    out: list[dict[str, Any]] = []
    for s in tail:
        data = s.data or {}
        out.append(
            {
                "sprint_id": str(s.id),
                "titulo": s.titulo,
                "velocidad_planeada": data.get("velocidad_planeada"),
                "velocidad_real": data.get("velocidad_real"),
                "fecha_fin": s.fecha_fin.isoformat() if s.fecha_fin else None,
            }
        )
    return out
