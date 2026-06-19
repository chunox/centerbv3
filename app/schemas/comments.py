from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

EntidadTipo = Literal["feature", "tarea", "feature_query", "feature_report"]


class CommentCreate(BaseModel):
    entidad_tipo: EntidadTipo
    entidad_id: UUID
    contenido: str = Field(min_length=1)
    estado_momento: str | None = Field(default=None, max_length=40)


class CommentRead(BaseModel):
    id: UUID
    entidad_tipo: EntidadTipo
    entidad_id: UUID
    user_id: UUID
    contenido: str
    estado_momento: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
