from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ProjectTipo = Literal["con_cliente", "interno"]
ProjectEstado = Literal["activo", "cerrado", "cancelado"]
MemberRol = Literal["cliente", "pm", "dev", "qa"]


class ProjectCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    descripcion: str | None = None
    tipo: ProjectTipo = "con_cliente"
    estado: ProjectEstado = "activo"
    fecha_inicio: date
    fecha_fin: date
    created_by: UUID

    @model_validator(mode="after")
    def fechas_coherentes(self) -> ProjectCreate:
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin debe ser mayor o igual que fecha_inicio")
        return self


class ProjectUpdate(BaseModel):
    actor_user_id: UUID
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    descripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None


class ProjectRead(BaseModel):
    id: UUID
    nombre: str
    descripcion: str | None
    tipo: ProjectTipo
    estado: ProjectEstado
    fecha_inicio: date
    fecha_fin: date
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectEstadoAction(BaseModel):
    action: Literal["cerrar", "reabrir", "cancelar"]
    actor_user_id: UUID


class ProjectMemberCreate(BaseModel):
    actor_user_id: UUID
    user_id: UUID
    rol: MemberRol


class ProjectMemberUpdate(BaseModel):
    actor_user_id: UUID
    rol: MemberRol


class ProjectMemberRead(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    rol: MemberRol
    joined_at: datetime

    model_config = {"from_attributes": True}
