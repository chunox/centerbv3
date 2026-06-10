from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

FeatureTipo = Literal["desarrollo", "bug", "mejora"]
FeaturePrioridad = Literal["baja", "media", "alta", "critica"]
FeatureEstado = Literal[
    "pendiente",
    "en_progreso",
    "uat",
    "esperando_liberacion_pm",
    "esperando_validacion_cliente",
    "completado",
    "cancelado",
]


class FeatureCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    descripcion: str | None = None
    tipo: FeatureTipo = "desarrollo"
    prioridad: FeaturePrioridad = "media"
    fecha_inicio: date
    fecha_fin: date
    duracion_estimada: int | None = Field(default=None, ge=1)
    estado: FeatureEstado = "pendiente"
    origen_feature_id: UUID | None = None
    created_by: UUID

    @model_validator(mode="after")
    def validar_reglas(self) -> FeatureCreate:
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin debe ser mayor o igual que fecha_inicio")
        if self.tipo == "mejora" and self.duracion_estimada is None:
            raise ValueError("duracion_estimada es obligatoria cuando tipo es mejora")
        return self


MemberRol = Literal["pm", "dev", "qa", "cliente"]

FeatureAction = Literal[
    "pasar_a_uat",
    "cancelar",
    "enviar_al_pm",
    "devolver_rework",
    "liberar_cliente",
    "rechazar_liberacion",
    "confirmar",
    "no_funciona",
    "completar",
]


class FeatureUpdate(BaseModel):
    actor_user_id: UUID
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    descripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    prioridad: FeaturePrioridad | None = None
    duracion_estimada: int | None = Field(default=None, ge=1)


class FeatureMigrateRequest(BaseModel):
    actor_user_id: UUID
    target_milestone_id: UUID


class FeatureActionRequest(BaseModel):
    action: FeatureAction
    actor_user_id: UUID
    form_data: dict[str, object] | None = None


class UatGateRead(BaseModel):
    can_pass_to_uat: bool
    active_tasks: int
    ready_for_test_tasks: int
    bloqueada: bool
    estado: FeatureEstado
    reasons: list[str] = Field(default_factory=list)


class FeatureRead(BaseModel):
    id: UUID
    milestone_id: UUID
    project_id: UUID
    nombre: str
    descripcion: str | None
    tipo: FeatureTipo
    prioridad: FeaturePrioridad
    fecha_inicio: date
    fecha_fin: date
    duracion_estimada: int | None
    estado: FeatureEstado
    bloqueada: bool
    origen_report_id: UUID | None
    origen_feature_id: UUID | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
