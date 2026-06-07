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

    model_config = {"from_attributes": True}
