from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ProjectTipo = Literal["con_cliente", "interno", "freestyle"]
ProjectEstado = Literal["activo", "cerrado", "cancelado"]
MemberRol = Literal["cliente", "pm", "dev", "qa"]
ProjectTemplateSlug = Literal[
    "t1_cliente_clasico",
    "t2_cliente_pm_tecnico",
    "t3_interno_clasico",
    "t4_interno_pm_tecnico",
    "t5_freestyle",
]


class ProjectCreate(BaseModel):
    organization_id: UUID
    nombre: str = Field(min_length=1, max_length=150)
    descripcion: str | None = None
    template_slug: ProjectTemplateSlug | None = None
    tipo: ProjectTipo | None = None
    estado: ProjectEstado = "activo"
    fecha_inicio: date
    fecha_fin: date
    created_by: UUID

    @model_validator(mode="after")
    def fechas_coherentes(self) -> ProjectCreate:
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin debe ser mayor o igual que fecha_inicio")
        return self

    @model_validator(mode="after")
    def resolve_template_slug(self) -> ProjectCreate:
        if self.template_slug is not None:
            return self
        if self.tipo == "interno":
            self.template_slug = "t3_interno_clasico"
        else:
            self.template_slug = "t1_cliente_clasico"
        return self


class ProjectUpdate(BaseModel):
    actor_user_id: UUID
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    descripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None


class ProjectTemplateRead(BaseModel):
    slug: str
    nombre: str
    descripcion: str
    tipo: ProjectTipo
    roles: list[str]
    creator_role: str
    orden: int


class ProjectRead(BaseModel):
    id: UUID
    organization_id: UUID
    nombre: str
    descripcion: str | None
    tipo: ProjectTipo
    template_slug: str
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
    role_id: UUID | None = None
    rol: str | None = None

    @model_validator(mode="after")
    def role_ref(self) -> ProjectMemberCreate:
        if self.role_id is None and self.rol is None:
            raise ValueError("Se requiere role_id o rol")
        return self


class ProjectMemberUpdate(BaseModel):
    actor_user_id: UUID
    role_id: UUID | None = None
    rol: str | None = None


class ProjectMemberRead(BaseModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    role_id: UUID
    role_slug: str
    role_nombre: str
    rol: MemberRol | None = None
    joined_at: datetime

    model_config = {"from_attributes": True}
