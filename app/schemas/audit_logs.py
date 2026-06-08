from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.audit import AuditAccion, AuditEntidadTipo


class AuditLogCreate(BaseModel):
    user_id: UUID
    entidad_tipo: AuditEntidadTipo
    entidad_id: UUID
    accion: AuditAccion
    campo: str | None = Field(default=None, max_length=100)
    valor_anterior: str | None = None
    valor_nuevo: str | None = None


class AuditLogRead(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    user_nombre: str | None = Field(default=None, serialization_alias="userNombre")
    entidad_tipo: AuditEntidadTipo
    entidad_id: UUID
    accion: AuditAccion
    campo: str | None
    valor_anterior: str | None
    valor_nuevo: str | None
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
