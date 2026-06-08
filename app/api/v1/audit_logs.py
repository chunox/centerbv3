"""
Registro de auditoría por proyecto.

GET filtra por viewer_rol (pm/dev/qa/cliente) según entidades visibles para cada rol.
Usado por la vista Actividad del frontend PM.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.models.entities import (
    AuditLog,
    Comment,
    Document,
    Feature,
    FeatureQuery,
    FeatureReport,
    Milestone,
    Task,
    User,
)
from app.schemas.audit_logs import AuditLogCreate, AuditLogRead
from app.schemas.projects import MemberRol
from app.services.access import filter_audit_logs_for_viewer
from app.services.audit import AuditEntidadTipo, record_audit_log

router = APIRouter(tags=["audit-logs"])


def _validate_entidad_in_project(
    entidad_tipo: AuditEntidadTipo,
    entidad_id: UUID,
    project_id: UUID,
    db: Session,
) -> None:
    if entidad_tipo == "feature":
        row = db.get(Feature, entidad_id)
        if not row or row.project_id != project_id:
            raise HTTPException(status_code=404, detail="Feature no encontrada en el proyecto")
        return
    if entidad_tipo == "tarea":
        row = db.get(Task, entidad_id)
        if not row or row.project_id != project_id:
            raise HTTPException(status_code=404, detail="Tarea no encontrada en el proyecto")
        return
    if entidad_tipo == "milestone":
        row = db.get(Milestone, entidad_id)
        if not row or row.project_id != project_id:
            raise HTTPException(status_code=404, detail="Milestone no encontrado en el proyecto")
        return
    if entidad_tipo == "document":
        row = db.get(Document, entidad_id)
        if not row or row.project_id != project_id:
            raise HTTPException(status_code=404, detail="Documento no encontrado en el proyecto")
        return
    if entidad_tipo == "feature_query":
        row = db.get(FeatureQuery, entidad_id)
        if not row:
            raise HTTPException(status_code=404, detail="Consulta no encontrada")
        feature = db.get(Feature, row.feature_id)
        if not feature or feature.project_id != project_id:
            raise HTTPException(status_code=404, detail="Consulta no pertenece al proyecto")
        return
    if entidad_tipo == "feature_report":
        row = db.get(FeatureReport, entidad_id)
        if not row:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        feature = db.get(Feature, row.feature_id)
        if not feature or feature.project_id != project_id:
            raise HTTPException(status_code=404, detail="Reporte no pertenece al proyecto")
        return
    if entidad_tipo == "comment":
        if not db.get(Comment, entidad_id):
            raise HTTPException(status_code=404, detail="Comentario no encontrado")
        return


@router.get("/{project_id}/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    project_id: UUID,
    entidad_tipo: AuditEntidadTipo | None = Query(default=None),
    entidad_id: UUID | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    viewer_user_id: UUID | None = Query(
        default=None,
        description="Usuario demo que consulta (sin JWT)",
    ),
    viewer_rol: MemberRol | None = Query(
        default=None,
        description="Rol demo del usuario que consulta",
    ),
    db: Session = Depends(get_db),
):
    get_project_or_404(project_id, db)
    stmt = select(AuditLog).where(AuditLog.project_id == project_id)
    if entidad_tipo is not None:
        stmt = stmt.where(AuditLog.entidad_tipo == entidad_tipo)
    if entidad_id is not None:
        stmt = stmt.where(AuditLog.entidad_id == entidad_id)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    stmt = stmt.order_by(AuditLog.created_at.desc())
    logs = list(db.scalars(stmt))
    return filter_audit_logs_for_viewer(
        db,
        logs,
        viewer_user_id=viewer_user_id,
        viewer_rol=viewer_rol,
    )


@router.post("/{project_id}/audit-logs", response_model=AuditLogRead, status_code=201)
def create_audit_log(
    project_id: UUID,
    payload: AuditLogCreate,
    db: Session = Depends(get_db),
):
    get_project_or_404(project_id, db)
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    _validate_entidad_in_project(
        payload.entidad_tipo, payload.entidad_id, project_id, db
    )

    entry = record_audit_log(
        db,
        project_id=project_id,
        user_id=payload.user_id,
        entidad_tipo=payload.entidad_tipo,
        entidad_id=payload.entidad_id,
        accion=payload.accion,
        campo=payload.campo,
        valor_anterior=payload.valor_anterior,
        valor_nuevo=payload.valor_nuevo,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/{project_id}/audit-logs/{log_id}", response_model=AuditLogRead)
def get_audit_log(
    project_id: UUID, log_id: UUID, db: Session = Depends(get_db)
):
    get_project_or_404(project_id, db)
    entry = db.get(AuditLog, log_id)
    if not entry or entry.project_id != project_id:
        raise HTTPException(status_code=404, detail="Registro de auditoría no encontrado")
    return entry
