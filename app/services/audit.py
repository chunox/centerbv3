import uuid
from typing import Literal

from sqlalchemy.orm import Session

from app.models.entities import AuditLog

AuditEntidadTipo = Literal[
    "feature",
    "tarea",
    "milestone",
    "feature_query",
    "feature_report",
    "comment",
    "document",
    "project",
    "hub_entry",
]
AuditAccion = Literal[
    "created",
    "updated",
    "deleted",
    "estado_changed",
    "bloqueada",
    "desbloqueada",
    "cancelada",
    "migrada",
    "feature_generada",
    "dependency_added",
    "dependency_removed",
]


def record_audit_log(
    db: Session,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    entidad_tipo: AuditEntidadTipo,
    entidad_id: uuid.UUID,
    accion: AuditAccion,
    campo: str | None = None,
    valor_anterior: str | None = None,
    valor_nuevo: str | None = None,
) -> AuditLog:
    """Registra una entrada de auditoría (append-only)."""
    entry = AuditLog(
        project_id=project_id,
        user_id=user_id,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        accion=accion,
        campo=campo,
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
    )
    db.add(entry)
    return entry
