from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, computed_field, model_validator

from app.domain.project_templates import project_tipo_for_template
from app.schemas.project_structure import ProjectStructureDef

ProjectTipo = Literal["con_cliente", "interno", "freestyle"]
TemplateDeliveryMode = Literal["waterfall", "scrum"]
ProjectEstado = Literal["activo", "cerrado", "cancelado"]
MemberRol = Literal["cliente", "pm", "dev", "qa"]
ProjectTemplateSlug = Literal[
    "t1_cliente_clasico",
    "t2_cliente_pm_tecnico",
    "t3_interno_clasico",
    "t4_interno_pm_tecnico",
    "t5_freestyle",
    "t6_scrum_interno",
    "t7_scrum_cliente",
]


class ProjectCreate(BaseModel):
    organization_id: UUID
    nombre: str = Field(min_length=1, max_length=150)
    descripcion: str | None = None
    pack_slug: str | None = None
    template_slug: ProjectTemplateSlug | None = None
    tipo: ProjectTipo | None = None
    estado: ProjectEstado = "activo"
    fecha_inicio: date
    fecha_fin: date
    project_structure: ProjectStructureDef | None = None

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
        elif self.tipo == "freestyle":
            self.template_slug = "t5_freestyle"
        else:
            self.template_slug = "t1_cliente_clasico"
        return self


class ProjectUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    descripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None


class ProjectTemplateRead(BaseModel):
    slug: str
    nombre: str
    descripcion: str
    tipo: ProjectTipo
    delivery_mode: TemplateDeliveryMode
    roles: list[str]
    creator_role: str
    orden: int


class ProjectRead(BaseModel):
    id: UUID
    organization_id: UUID
    nombre: str
    descripcion: str | None
    template_slug: str
    pack_slug: str = "software"
    structure_version: int = 2
    estado: ProjectEstado
    fecha_inicio: date
    fecha_fin: date
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tipo(self) -> ProjectTipo:
        legacy = project_tipo_for_template(
            self.template_slug,
            pack_slug=self.pack_slug,
        )
        return legacy  # type: ignore[return-value]


class ProjectEstadoAction(BaseModel):
    action: Literal["cerrar", "reabrir", "cancelar"]


class ProjectMemberCreate(BaseModel):
    user_id: UUID
    role_id: UUID | None = None
    rol: str | None = None

    @model_validator(mode="after")
    def role_ref(self) -> ProjectMemberCreate:
        if self.role_id is None and self.rol is None:
            raise ValueError("Se requiere role_id o rol")
        return self


class ProjectMemberUpdate(BaseModel):
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
