from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ReportTipo = Literal["bug", "mejora"]
ReportEstado = Literal["pendiente", "aprobado", "rechazado"]


class FeatureReportCreate(BaseModel):
    tipo: ReportTipo
    descripcion: str = Field(min_length=1)
    reported_by: UUID


class FeatureReportAction(BaseModel):
    action: Literal["aprobar", "rechazar"]
    actor_user_id: UUID
    duracion_estimada: int | None = Field(default=None, ge=1)
    nombre_feature: str | None = Field(default=None, max_length=150)


class FeatureReportRead(BaseModel):
    id: UUID
    feature_id: UUID
    reported_by: UUID
    tipo: ReportTipo
    descripcion: str
    estado: ReportEstado
    generated_feature_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeatureReportInboxRead(FeatureReportRead):
    """Bandeja PM / Cliente — reporte con contexto de la feature original."""

    project_id: UUID
    milestone_id: UUID
    feature_nombre: str
    feature_estado: str
