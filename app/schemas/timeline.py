from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TimelineEventSource = Literal["audit", "comment"]
TimelinePlanTipo = Literal["milestone", "feature"]


class TimelineEventRead(BaseModel):
    """Evento puntual: auditoría o comentario."""

    id: UUID
    source: TimelineEventSource
    occurred_at: datetime
    user_id: UUID
    user_nombre: str
    entidad_tipo: str
    entidad_id: UUID
    titulo: str
    accion: str | None = None
    campo: str | None = None
    valor_anterior: str | None = None
    valor_nuevo: str | None = None
    contenido: str | None = None
    estado_momento: str | None = None
    milestone_id: UUID | None = None
    milestone_nombre: str | None = None
    feature_id: UUID | None = None
    feature_nombre: str | None = None


class TimelinePlanItemRead(BaseModel):
    """Tramo planificado del cronograma (hito o feature)."""

    id: UUID
    tipo: TimelinePlanTipo
    nombre: str
    fecha_inicio: date
    fecha_fin: date
    estado: str
    milestone_id: UUID
    milestone_nombre: str | None = None
    feature_tipo: str | None = None
    orden: int | None = None


class ProjectTimelineRead(BaseModel):
    eventos: list[TimelineEventRead] = Field(default_factory=list)
    plan: list[TimelinePlanItemRead] = Field(default_factory=list)
