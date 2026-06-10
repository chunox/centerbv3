from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

QueryEstado = Literal[
    "borrador",
    "pendiente_aprobacion_pm",
    "esperando_cliente",
    "respuesta_cliente",
    "esperando_pm",
    "cerrada",
    "rechazada",
]

QueryAction = Literal[
    "solicitar_envio",
    "aprobar_envio",
    "activar",
    "activar_cliente",
    "activar_interno",
    "responder",
    "validar_aceptar",
    "validar_rechazar",
    "cerrar",
    "cerrar_directo",
    "rechazar",
]

MemberRol = Literal["pm", "dev", "qa", "cliente"]


class FeatureQueryCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=255)
    descripcion: str = Field(min_length=1)
    created_by: UUID


class FeatureQueryRead(BaseModel):
    id: UUID
    feature_id: UUID
    titulo: str
    descripcion: str
    estado: QueryEstado
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeatureQueryAction(BaseModel):
    action: QueryAction
    actor_user_id: UUID
    form_data: dict[str, object] | None = None


class FeatureQueryInboxRead(FeatureQueryRead):
    project_id: UUID
    milestone_id: UUID
    feature_nombre: str
