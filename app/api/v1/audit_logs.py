"""
Registro de auditoría por proyecto.

GET filtra por capacidades del usuario autenticado.
Usado por la vista Actividad del frontend PM.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import get_current_actor_id
from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.models.entities import AuditLog, Comment, HubEntry
from app.schemas.audit_logs import AuditLogCreate, AuditLogRead
from app.services.audit_display import audit_log_to_read, audit_logs_to_read
from app.services.access import resolve_audit_logs_for_user
from app.services.audit import AuditEntidadTipo, record_audit_log
from app.services.record_validation import AUDIT_RECORD_TYPE, assert_project_record

router = APIRouter(tags=["audit-logs"])


def _validate_entidad_in_project(
    entidad_tipo: AuditEntidadTipo,
    entidad_id: UUID,
    project_id: UUID,
    db: Session,
) -> None:
    record_type = AUDIT_RECORD_TYPE.get(entidad_tipo)
    if record_type is not None:
        assert_project_record(
            db,
            record_id=entidad_id,
            project_id=project_id,
            record_type=record_type,
            detail=f"Entidad {entidad_tipo} no encontrada en el proyecto",
        )
        return
    if entidad_tipo == "hub_entry":
        row = db.get(HubEntry, entidad_id)
        if not row or row.project_id != project_id:
            raise HTTPException(status_code=404, detail="Publicación no encontrada en el proyecto")
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
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    actor_user_id: UUID = Depends(get_current_actor_id),
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
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    logs = list(db.scalars(stmt))
    visible = resolve_audit_logs_for_user(
        db,
        logs,
        project_id=project_id,
        viewer_user_id=actor_user_id,
    )
    return audit_logs_to_read(db, visible)


@router.post("/{project_id}/audit-logs", response_model=AuditLogRead, status_code=201)
def create_audit_log(
    project_id: UUID,
    payload: AuditLogCreate,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    get_project_or_404(project_id, db)

    _validate_entidad_in_project(
        payload.entidad_tipo, payload.entidad_id, project_id, db
    )

    entry = record_audit_log(
        db,
        project_id=project_id,
        user_id=actor_user_id,
        entidad_tipo=payload.entidad_tipo,
        entidad_id=payload.entidad_id,
        accion=payload.accion,
        campo=payload.campo,
        valor_anterior=payload.valor_anterior,
        valor_nuevo=payload.valor_nuevo,
    )
    db.commit()
    db.refresh(entry)
    return audit_log_to_read(db, entry)


@router.get("/{project_id}/audit-logs/{log_id}", response_model=AuditLogRead)
def get_audit_log(
    project_id: UUID,
    log_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    get_project_or_404(project_id, db)
    entry = db.get(AuditLog, log_id)
    if not entry or entry.project_id != project_id:
        raise HTTPException(status_code=404, detail="Registro de auditoría no encontrado")
    visible = resolve_audit_logs_for_user(
        db,
        [entry],
        project_id=project_id,
        viewer_user_id=actor_user_id,
    )
    if not visible:
        raise HTTPException(status_code=403, detail="Sin permiso para ver este registro")
    return audit_log_to_read(db, visible[0])
