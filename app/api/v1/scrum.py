"""Endpoints Scrum: soporte de planning, métricas y ceremonias."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import get_current_actor_id
from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.domain.capabilities import (
    WORKBENCH_SCRUM_CAPACITY,
    WORKBENCH_SCRUM_IMPEDIMENTS,
    WORKBENCH_SPRINT_BOARD,
)
from app.models.entities import (
    AuditLog,
    ProjectRecord,
    ScrumCeremonyEntry,
    ScrumCeremonySession,
)
from app.services.scrum_ceremonies import (
    create_entry,
    create_session,
    delete_entry,
    delete_session,
    list_entries,
    list_sessions,
    update_entry,
    update_session,
)
from app.services.scrum_effort import batch_feature_effort_hours
from app.services.scrum_metrics import list_sprint_velocity, sync_sprint_horas_completadas
from app.services.scrum_structure import list_features_for_sprint
from app.services.workflow.authorize import assert_capability

router = APIRouter(prefix="/projects", tags=["scrum"])


class ScrumImpedimentCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=255)
    sprint_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    impacto: str | None = None


class ScrumImpedimentResolve(BaseModel):
    resolucion: str | None = None


class SprintCapacityUpdate(BaseModel):
    capacity_plan: list[dict[str, Any]]


class ScrumSessionCreate(BaseModel):
    session_type: str
    title: str | None = None
    sprint_id: uuid.UUID | None = None
    status: str = "planned"
    facilitator_user_id: uuid.UUID | None = None


class ScrumSessionPatch(BaseModel):
    session_type: str | None = None
    title: str | None = None
    sprint_id: uuid.UUID | None = None
    status: str | None = None
    facilitator_user_id: uuid.UUID | None = None


class ScrumSessionEntryCreate(BaseModel):
    entry_type: str = "note"
    payload: dict[str, Any] = Field(default_factory=dict)


class ScrumSessionEntryPatch(BaseModel):
    entry_type: str | None = None
    payload: dict[str, Any] | None = None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _capacity_available_horas(entry: dict[str, Any]) -> float:
    committed = _to_float(entry.get("committed_h"))
    if committed is not None:
        return max(committed, 0.0)
    dias = max(_to_float(entry.get("dias")) or 0.0, 0.0)
    pto_dias = max(_to_float(entry.get("pto_dias")) or 0.0, 0.0)
    focus_pct = max(min(_to_float(entry.get("focus_pct")) or 100.0, 100.0), 0.0)
    return round(dias * pto_dias * (focus_pct / 100.0), 2)


def _serialize_session(row: ScrumCeremonySession) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "sprint_id": str(row.sprint_id) if row.sprint_id else None,
        "session_type": row.session_type,
        "title": row.title,
        "status": row.status,
        "facilitator_user_id": str(row.facilitator_user_id) if row.facilitator_user_id else None,
        "created_by": str(row.created_by),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _serialize_entry(row: ScrumCeremonyEntry) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "session_id": str(row.session_id),
        "author_user_id": str(row.author_user_id),
        "entry_type": row.entry_type,
        "payload": row.payload or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/{project_id}/scrum/sprints")
def list_sprints(
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    sprints = list(
        db.scalars(
            select(ProjectRecord)
            .where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type.in_(("sprint", "milestone")),
            )
            .order_by(ProjectRecord.orden.asc(), ProjectRecord.created_at.asc())
        )
    )
    from app.services.scrum_v2_structure import is_sprint_record

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
            "capacity_plan": (s.data or {}).get("capacity_plan") or [],
            "velocidad_planeada": (s.data or {}).get("horas_planeadas"),
            "velocidad_real": (s.data or {}).get("horas_completadas"),
        }
        for s in sprints
        if is_sprint_record(s)
    ]


@router.get("/{project_id}/scrum/sprints/{sprint_id}/burndown")
def get_sprint_burndown(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)

    sprint = db.get(ProjectRecord, sprint_id)
    if sprint is None or sprint.project_id != project.id:
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

    # Historias v2: record_type=task → audit entidad_tipo=tarea; legacy feature → feature.
    # valor_nuevo incluye action_id: "completado (completar)".
    story_audit_tipos = ("feature", "task", "tarea")
    completions = list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.project_id == project.id,
                AuditLog.entidad_tipo.in_(story_audit_tipos),
                AuditLog.campo == "estado",
                AuditLog.valor_nuevo.like("completado%"),
                AuditLog.entidad_id.in_(feature_ids),
            )
        )
    ) if feature_ids else []

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
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    limit: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    return list_sprint_velocity(db, project.id, limit=limit)


@router.get("/{project_id}/scrum/impediments")
def get_scrum_impediments(
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    sprint_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SCRUM_IMPEDIMENTS)
    rows = list(
        db.scalars(
            select(ProjectRecord)
            .where(
                ProjectRecord.project_id == project.id,
                ProjectRecord.record_type == "impediment",
            )
            .order_by(ProjectRecord.created_at.desc())
        )
    )
    out: list[dict[str, Any]] = []
    sprint_id_str = str(sprint_id) if sprint_id else None
    for row in rows:
        data = row.data or {}
        if sprint_id_str and str(data.get("sprint_id") or "") != sprint_id_str:
            continue
        out.append(
            {
                "id": str(row.id),
                "titulo": row.titulo,
                "estado": row.estado,
                "data": data,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
        )
    return out


@router.post("/{project_id}/scrum/impediments")
def post_scrum_impediment(
    project_id: uuid.UUID,
    payload: ScrumImpedimentCreate,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SCRUM_IMPEDIMENTS)
    now_iso = date.today().isoformat()
    data = {
        "titulo": payload.titulo.strip(),
        "sprint_id": str(payload.sprint_id) if payload.sprint_id else None,
        "owner_user_id": str(payload.owner_user_id) if payload.owner_user_id else None,
        "status": "open",
        "impacto": payload.impacto,
        "resolucion": None,
        "raised_at": now_iso,
    }
    row = ProjectRecord(
        project_id=project.id,
        record_type="impediment",
        parent_id=payload.sprint_id,
        titulo=payload.titulo.strip(),
        descripcion=payload.impacto,
        estado="open",
        data=data,
        created_by=actor_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "titulo": row.titulo, "estado": row.estado, "data": row.data or {}}


@router.post("/{project_id}/scrum/impediments/{impediment_id}/resolve")
def post_scrum_impediment_resolve(
    project_id: uuid.UUID,
    impediment_id: uuid.UUID,
    payload: ScrumImpedimentResolve,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SCRUM_IMPEDIMENTS)
    row = db.get(ProjectRecord, impediment_id)
    if row is None or row.project_id != project.id or row.record_type != "impediment":
        raise HTTPException(status_code=404, detail="Impedimento no encontrado")
    data = dict(row.data or {})
    data["status"] = "resolved"
    data["resolucion"] = payload.resolucion
    row.estado = "resolved"
    row.data = data
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "estado": row.estado, "data": row.data or {}}


@router.get("/{project_id}/scrum/sprints/{sprint_id}/capacity")
def get_scrum_sprint_capacity(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SCRUM_CAPACITY)
    from app.services.scrum_v2_structure import is_sprint_record

    sprint = db.get(ProjectRecord, sprint_id)
    if sprint is None or sprint.project_id != project.id or not is_sprint_record(sprint):
        raise HTTPException(status_code=404, detail="Sprint no encontrado")
    data = sprint.data or {}
    plan = data.get("capacity_plan") or []
    if not isinstance(plan, list):
        plan = []
    total = round(sum(_capacity_available_horas(p) for p in plan if isinstance(p, dict)), 2)
    return {
        "sprint_id": str(sprint.id),
        "capacity_plan": plan,
        "available_horas": total,
        "horas_planeadas": data.get("horas_planeadas"),
    }


@router.put("/{project_id}/scrum/sprints/{sprint_id}/capacity")
def put_scrum_sprint_capacity(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    payload: SprintCapacityUpdate,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SCRUM_CAPACITY)
    from app.services.scrum_v2_structure import is_sprint_record

    sprint = db.get(ProjectRecord, sprint_id)
    if sprint is None or sprint.project_id != project.id or not is_sprint_record(sprint):
        raise HTTPException(status_code=404, detail="Sprint no encontrado")
    clean_plan = [dict(item) for item in payload.capacity_plan if isinstance(item, dict)]
    total = round(sum(_capacity_available_horas(p) for p in clean_plan), 2)
    data = dict(sprint.data or {})
    data["capacity_plan"] = clean_plan
    data["horas_planeadas"] = total
    sprint.data = data
    db.commit()
    db.refresh(sprint)
    return {
        "sprint_id": str(sprint.id),
        "capacity_plan": clean_plan,
        "available_horas": total,
        "horas_planeadas": total,
    }


@router.post("/{project_id}/scrum/sprints/{sprint_id}/sync-velocity")
def post_sync_sprint_velocity(
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)

    sprint = db.get(ProjectRecord, sprint_id)
    if sprint is None or sprint.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sprint no encontrado")

    total = sync_sprint_horas_completadas(db, sprint)
    return {
        "sprint_id": str(sprint_id),
        "horas_completadas": total,
        "velocidad_real": total,
    }


@router.get("/{project_id}/scrum/sessions")
def get_scrum_sessions(
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    session_type: str | None = Query(None),
    sprint_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    rows = list_sessions(db, project.id, session_type=session_type, sprint_id=sprint_id)
    return [_serialize_session(row) for row in rows]


@router.post("/{project_id}/scrum/sessions")
def post_scrum_session(
    project_id: uuid.UUID,
    payload: ScrumSessionCreate,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    row = create_session(
        db,
        project_id=project.id,
        actor_user_id=actor_user_id,
        session_type=payload.session_type,
        title=payload.title or payload.session_type.replace("_", " ").title(),
        sprint_id=payload.sprint_id,
        status=payload.status,
        facilitator_user_id=payload.facilitator_user_id,
    )
    db.commit()
    db.refresh(row)
    return _serialize_session(row)


@router.patch("/{project_id}/scrum/sessions/{session_id}")
def patch_scrum_session(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: ScrumSessionPatch,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    row = db.get(ScrumCeremonySession, session_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    patch = payload.model_dump(exclude_none=False)
    updated = update_session(db, session=row, patch=patch)
    db.commit()
    db.refresh(updated)
    return _serialize_session(updated)


@router.delete("/{project_id}/scrum/sessions/{session_id}")
def delete_scrum_session(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    row = db.get(ScrumCeremonySession, session_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    delete_session(db, row)
    db.commit()
    return {"ok": True}


@router.get("/{project_id}/scrum/sessions/{session_id}/entries")
def get_scrum_session_entries(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    session = db.get(ScrumCeremonySession, session_id)
    if session is None or session.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    rows = list_entries(db, session_id)
    return [_serialize_entry(row) for row in rows]


@router.post("/{project_id}/scrum/sessions/{session_id}/entries")
def post_scrum_session_entry(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: ScrumSessionEntryCreate,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    session = db.get(ScrumCeremonySession, session_id)
    if session is None or session.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    row = create_entry(
        db,
        session_id=session_id,
        author_user_id=actor_user_id,
        entry_type=payload.entry_type,
        payload=payload.payload,
    )
    db.commit()
    db.refresh(row)
    return _serialize_entry(row)


@router.patch("/{project_id}/scrum/sessions/{session_id}/entries/{entry_id}")
def patch_scrum_session_entry(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: ScrumSessionEntryPatch,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    session = db.get(ScrumCeremonySession, session_id)
    if session is None or session.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    entry = db.get(ScrumCeremonyEntry, entry_id)
    if entry is None or entry.session_id != session_id:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    row = update_entry(
        db,
        entry=entry,
        entry_type=payload.entry_type,
        payload=payload.payload,
    )
    db.commit()
    db.refresh(row)
    return _serialize_entry(row)


@router.delete("/{project_id}/scrum/sessions/{session_id}/entries/{entry_id}")
def delete_scrum_session_entry(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    entry_id: uuid.UUID,
    actor_user_id: uuid.UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    project = get_project_or_404(project_id, db)
    assert_capability(db, project.id, actor_user_id, WORKBENCH_SPRINT_BOARD)
    session = db.get(ScrumCeremonySession, session_id)
    if session is None or session.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    entry = db.get(ScrumCeremonyEntry, entry_id)
    if entry is None or entry.session_id != session_id:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    delete_entry(db, entry)
    db.commit()
    return {"ok": True}
