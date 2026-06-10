from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MemberRol = Literal["pm", "dev", "qa", "cliente"]

TaskEstado = Literal[
    "backlog",
    "to_do",
    "in_progress",
    "ready_for_test",
    "completed",
    "cancel",
]


class TaskCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=255)
    descripcion: str | None = None
    estado: TaskEstado = "backlog"
    asignado_ids: list[UUID] = Field(default_factory=list)
    created_by: UUID


class TaskSubtaskCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=255)
    descripcion: str | None = None
    estado: TaskEstado = "backlog"
    actor_user_id: UUID


class TaskMove(BaseModel):
    estado: TaskEstado
    actor_user_id: UUID


class TaskUpdate(BaseModel):
    actor_user_id: UUID
    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    descripcion: str | None = None
    asignado_ids: list[UUID] | None = None


class TaskRead(BaseModel):
    id: UUID
    feature_id: UUID
    project_id: UUID
    titulo: str
    descripcion: str | None
    estado: TaskEstado
    asignado_ids: list[UUID]
    created_by: UUID
    parent_task_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

