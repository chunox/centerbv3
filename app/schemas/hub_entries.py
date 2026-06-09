from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

HubEntryTipo = Literal["update", "note"]
HubEntryVisibilidad = Literal["publico", "interno"]


class HubEntryCreate(BaseModel):
    author_id: UUID
    tipo: HubEntryTipo
    titulo: str | None = Field(default=None, max_length=255)
    contenido: str = Field(min_length=1)
    visibilidad: HubEntryVisibilidad = "publico"

    @model_validator(mode="after")
    def validar_nota_titulo(self) -> HubEntryCreate:
        if self.tipo == "note" and not (self.titulo and self.titulo.strip()):
            raise ValueError("Las notas requieren título")
        return self


class HubEntryUpdate(BaseModel):
    actor_user_id: UUID
    titulo: str | None = Field(default=None, max_length=255)
    contenido: str | None = Field(default=None, min_length=1)
    visibilidad: HubEntryVisibilidad | None = None


class HubEntryRead(BaseModel):
    id: UUID
    project_id: UUID
    author_id: UUID
    author_nombre: str | None = None
    tipo: HubEntryTipo
    titulo: str | None
    contenido: str
    visibilidad: HubEntryVisibilidad
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
