from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

AttachmentEntidadTipo = Literal[
    "comment",
    "tarea",
    "feature",
    "feature_query",
    "feature_report",
    "hub_entry",
    "project",
    "pieza",
    "entregable",
    "campana",
]


class AttachmentCreate(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    nombre_original: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    tamano_bytes: int = Field(ge=1)
    entidad_tipo: AttachmentEntidadTipo
    entidad_id: UUID


class AttachmentRelationRead(BaseModel):
    id: UUID
    entidad_tipo: AttachmentEntidadTipo
    entidad_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class AttachmentUpdate(BaseModel):
    url: str | None = Field(default=None, min_length=1, max_length=500)
    nombre_original: str | None = Field(default=None, min_length=1, max_length=255)
    mime_type: str | None = Field(default=None, min_length=1, max_length=100)


class AttachmentRead(BaseModel):
    id: UUID
    url: str
    nombre_original: str
    mime_type: str
    tamano_bytes: int
    uploaded_by: UUID
    created_at: datetime
    relations: list[AttachmentRelationRead] = []

    model_config = {"from_attributes": True}
