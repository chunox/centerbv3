"""Enriquecimiento de audit logs para la UI (nombre del actor)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.entities import AuditLog, User
from app.schemas.audit_logs import AuditLogRead


def _user_nombre(db: Session, user_id: UUID, cache: dict[UUID, str | None]) -> str | None:
    if user_id not in cache:
        user = db.get(User, user_id)
        cache[user_id] = user.nombre if user else None
    return cache[user_id]


def audit_log_to_read(
    db: Session,
    log: AuditLog,
    *,
    cache: dict[UUID, str | None] | None = None,
) -> AuditLogRead:
    user_cache = cache if cache is not None else {}
    return AuditLogRead(
        id=log.id,
        project_id=log.project_id,
        user_id=log.user_id,
        user_nombre=_user_nombre(db, log.user_id, user_cache),
        entidad_tipo=log.entidad_tipo,
        entidad_id=log.entidad_id,
        accion=log.accion,
        campo=log.campo,
        valor_anterior=log.valor_anterior,
        valor_nuevo=log.valor_nuevo,
        created_at=log.created_at,
    )


def audit_logs_to_read(db: Session, logs: list[AuditLog]) -> list[AuditLogRead]:
    cache: dict[UUID, str | None] = {}
    return [audit_log_to_read(db, log, cache=cache) for log in logs]
