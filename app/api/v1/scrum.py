"""Endpoints Scrum: burndown y listado de sprints."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.domain.capabilities import WORKBENCH_SPRINT_BOARD
from app.models.entities import AuditLog, ProjectRecord
from app.services.scrum_metrics import list_sprint_velocity, sync_sprint_velocidad_real
from app.services.workflow.authorize import assert_capability

router = APIRouter(prefix="/projects", tags=["scrum"])


def _sp_value(sp_str: str | None) -> int:
    if sp_str is None or sp_str == "?":
        return 0
    try:
        return int(sp_str)
    except (ValueError, TypeError):
        return 0


@router.get("/{project_id}/scrum/sprints")
def list_sprints(
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    sprints = list(
        db.scalars(
            select(ProjectRecord)
            .where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "milestone",
            )
            .order_by(ProjectRecord.orden.asc(), ProjectRecord.created_at.asc())
        )
    )
    return [
        {
            "id": str(s.id),
            "titulo": s.titulo,
            "estado": s.estado,
            "fecha_inicio": s.fecha_inicio.isoformat() if s.fecha_inicio else None,
            "fecha_fin": s.fecha_fin.isoformat() if s.fecha_fin else None,
            "sprint_goal": (s.data or {}).get("sprint_goal"),
            "velocidad_planeada": (s.data or {}).get("velocidad_planeada"),
            "velocidad_real": (s.data or {}).get("velocidad_real"),
        }
        for s in sprints
    ]


@router.get("/{project_id}/scrum/sprints/{sprint_id}/burndown")
def get_sprint_burndown(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    actor_user_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)

    sprint = db.get(ProjectRecord, sprint_id)
    if sprint is None or sprint.project_id != project.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Sprint no encontrado")

    features = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.parent_id == sprint_id,
                ProjectRecord.record_type == "feature",
            )
        )
    )

    total_sp = sum(_sp_value((f.data or {}).get("story_points")) for f in features)
    feature_ids = {f.id for f in features}
    feature_sp: dict[uuid.UUID, int] = {
        f.id: _sp_value((f.data or {}).get("story_points")) for f in features
    }

    start: date = sprint.fecha_inicio or date.today()
    end: date = sprint.fecha_fin or date.today()
    if end < start:
        end = start

    total_days = max((end - start).days, 1)

    completions = list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.project_id == project.id,
                AuditLog.entidad_tipo == "feature",
                AuditLog.campo == "estado",
                AuditLog.valor_nuevo == "completado",
                AuditLog.entidad_id.in_(feature_ids),
            )
        )
    ) if feature_ids else []

    completed_sp_by_day: dict[date, int] = {}
    for log in completions:
        day = log.created_at.date()
        completed_sp_by_day[day] = completed_sp_by_day.get(day, 0) + feature_sp.get(
            log.entidad_id, 0
        )

    days: list[dict[str, Any]] = []
    cumulative_completed = 0
    for i in range(total_days + 1):
        current_day = start + timedelta(days=i)
        ideal = round(total_sp * (1 - i / total_days), 1)
        cumulative_completed += completed_sp_by_day.get(current_day, 0)
        actual = max(total_sp - cumulative_completed, 0)
        days.append(
            {
                "date": current_day.isoformat(),
                "ideal": ideal,
                "actual": actual if current_day <= date.today() else None,
            }
        )

    completed_sp = sum(
        feature_sp[f.id]
        for f in features
        if f.estado == "completado"
    )

    return {
        "sprint_id": str(sprint_id),
        "total_sp": total_sp,
        "completed_sp": completed_sp,
        "days": days,
    }


@router.get("/{project_id}/scrum/velocity")
def get_scrum_velocity(
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID = Query(...),
    limit: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    return list_sprint_velocity(db, project.id, limit=limit)


@router.post("/{project_id}/scrum/sprints/{sprint_id}/sync-velocity")
def post_sync_sprint_velocity(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    actor_user_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)

    sprint = db.get(ProjectRecord, sprint_id)
    if sprint is None or sprint.project_id != project.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Sprint no encontrado")

    total = sync_sprint_velocidad_real(db, sprint)
    return {
        "sprint_id": str(sprint_id),
        "velocidad_real": total,
    }
