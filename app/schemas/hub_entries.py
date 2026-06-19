from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

HubEntryTipo = Literal["update", "note", "shortcut", "page", "canvas"]


class HubEntryCreate(BaseModel):
    tipo: HubEntryTipo
    titulo: str | None = Field(default=None, max_length=255)
    contenido: str = Field(default="", min_length=0)
    visible_roles: list[str] = Field(default_factory=list)
    record_id: UUID | None = None

    @model_validator(mode="after")
    def validar_tipo(self) -> HubEntryCreate:
        if self.tipo == "note" and not (self.titulo and self.titulo.strip()):
            raise ValueError("Las notas requieren título")
        if self.tipo == "shortcut" and self.record_id is None:
            raise ValueError("Los shortcuts requieren record_id")
        if self.tipo in ("page", "canvas") and not (self.titulo and self.titulo.strip()):
            raise ValueError("Las páginas y canvas requieren título")
        return self


class HubEntryUpdate(BaseModel):
    titulo: str | None = Field(default=None, max_length=255)
    contenido: str | None = Field(default=None, min_length=0)
    visible_roles: list[str] | None = None
    record_id: UUID | None = None


class HubEntryRead(BaseModel):
    id: UUID
    project_id: UUID
    author_id: UUID
    author_nombre: str | None = None
    tipo: HubEntryTipo
    titulo: str | None
    contenido: str
    visible_roles: list[Any] = Field(default_factory=list)
    record_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
