from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from uuid import UUID

from pydantic import BaseModel, Field, model_validator

MilestoneTipo = Literal["entrega"]
MilestoneEstado = Literal[
    "pendiente",
    "en_progreso",
    "completado",
    "en_progreso_con_bug",
    "cerrado_con_bug",
    "cancelado",
]


class MilestoneCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    descripcion: str | None = None
    tipo: MilestoneTipo = "entrega"
    orden: int = Field(default=1, ge=1)
    fecha_inicio: date
    fecha_fin: date
    estado: MilestoneEstado = "pendiente"
    created_by: UUID

    @model_validator(mode="after")
    def fechas_coherentes(self) -> MilestoneCreate:
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin debe ser mayor o igual que fecha_inicio")
        return self


class MilestoneUpdate(BaseModel):
    actor_user_id: UUID
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    descripcion: str | None = None
    orden: int | None = Field(default=None, ge=1)
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    estado: MilestoneEstado | None = None


class MilestoneActionRequest(BaseModel):
    action: Literal["cancelar"] = "cancelar"
    actor_user_id: UUID
    actor_rol: Literal["pm"] = "pm"


class MilestoneRead(BaseModel):
    id: UUID
    project_id: UUID
    nombre: str
    descripcion: str | None
    tipo: MilestoneTipo
    orden: int
    fecha_inicio: date
    fecha_fin: date
    estado: MilestoneEstado
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
