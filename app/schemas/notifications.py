from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.services.notifications import NotificationEntidadTipo, NotificationTipo


class NotificationCreate(BaseModel):
    project_id: UUID
    tipo: NotificationTipo
    entidad_tipo: NotificationEntidadTipo
    entidad_id: UUID


class NotificationUpdate(BaseModel):
    leida: bool = True


class NotificationRead(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    tipo: NotificationTipo
    entidad_tipo: NotificationEntidadTipo
    entidad_id: UUID
    leida: bool
    created_at: datetime
    titulo: str | None = None
    mensaje: str | None = None
    entidad_nombre: str | None = None
    project_nombre: str | None = None
    actor_nombre: str | None = None

    model_config = {"from_attributes": True}
