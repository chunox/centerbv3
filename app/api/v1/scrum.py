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
from app.services.scrum_effort import batch_feature_effort_hours
from app.services.scrum_metrics import list_sprint_velocity, sync_sprint_horas_completadas
from app.services.scrum_structure import list_features_for_sprint
from app.services.workflow.authorize import assert_capability

router = APIRouter(prefix="/projects", tags=["scrum"])


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
            "horas_planeadas": (s.data or {}).get("horas_planeadas"),
            "horas_completadas": (s.data or {}).get("horas_completadas"),
            "velocidad_planeada": (s.data or {}).get("horas_planeadas"),
            "velocidad_real": (s.data or {}).get("horas_completadas"),
        }
        for s in sprints
        if (s.data or {}).get("tipo") != "product_backlog"
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

    features = list_features_for_sprint(db, project.id, sprint_id)
    feature_ids = [f.id for f in features]
    feature_horas = batch_feature_effort_hours(db, project.id, feature_ids)
    total_horas = sum(feature_horas.values())

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

    task_completions = list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.project_id == project.id,
                AuditLog.entidad_tipo == "task",
                AuditLog.campo == "estado",
                AuditLog.valor_nuevo == "completado",
                AuditLog.entidad_id.in_(feature_ids),
            )
        )
    ) if feature_ids else []
    completions = list(completions) + task_completions

    completed_horas_by_day: dict[date, float] = {}
    for log in completions:
        day = log.created_at.date()
        completed_horas_by_day[day] = completed_horas_by_day.get(day, 0.0) + feature_horas.get(
            log.entidad_id, 0.0
        )

    days: list[dict[str, Any]] = []
    cumulative_completed = 0.0
    for i in range(total_days + 1):
        current_day = start + timedelta(days=i)
        ideal = round(total_horas * (1 - i / total_days), 1)
        cumulative_completed += completed_horas_by_day.get(current_day, 0.0)
        actual = max(total_horas - cumulative_completed, 0.0)
        days.append(
            {
                "date": current_day.isoformat(),
                "ideal": ideal,
                "actual": actual if current_day <= date.today() else None,
            }
        )

    completed_horas = sum(
        feature_horas[f.id]
        for f in features
        if f.estado == "completado"
    )

    return {
        "sprint_id": str(sprint_id),
        "total_horas": total_horas,
        "completed_horas": completed_horas,
        "total_sp": total_horas,
        "completed_sp": completed_horas,
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

    total = sync_sprint_horas_completadas(db, sprint)
    return {
        "sprint_id": str(sprint_id),
        "horas_completadas": total,
        "velocidad_real": total,
    }
