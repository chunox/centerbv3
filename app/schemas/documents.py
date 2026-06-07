from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

DocumentVisibilidad = Literal["publico", "interno"]


class DocumentCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=255)
    contenido: str | None = None
    archivo_url: str | None = Field(default=None, max_length=500)
    visibilidad: DocumentVisibilidad = "publico"
    created_by: UUID


class DocumentUpdate(BaseModel):
    actor_user_id: UUID
    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    contenido: str | None = None
    archivo_url: str | None = Field(default=None, max_length=500)
    visibilidad: DocumentVisibilidad | None = None


class DocumentRead(BaseModel):
    id: UUID
    project_id: UUID
    titulo: str
    contenido: str | None
    archivo_url: str | None
    visibilidad: DocumentVisibilidad
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
