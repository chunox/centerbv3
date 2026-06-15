from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RecordRead(BaseModel):
    id: UUID
    project_id: UUID
    record_type: str
    titulo: str
    descripcion: str | None = None
    estado: str
    parent_id: UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    orden: int = 0
    assignee_ids: list[UUID] = Field(default_factory=list)
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RecordCreate(BaseModel):
    actor_user_id: UUID
    record_type: str
    titulo: str = Field(min_length=1, max_length=255)
    descripcion: str | None = None
    parent_id: UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    orden: int | None = None
    assignee_ids: list[UUID] = Field(default_factory=list)
    initial_state: str | None = None


class RecordMigrateRequest(BaseModel):
    actor_user_id: UUID
    target_milestone_id: UUID


class RecordUpdate(BaseModel):
    actor_user_id: UUID
    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    descripcion: str | None = None
    parent_id: UUID | None = None
    data: dict[str, Any] | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    orden: int | None = None
    assignee_ids: list[UUID] | None = None


class RecordTransitionRequest(BaseModel):
    actor_user_id: UUID
    action_id: str
    target_state: str | None = None
    form_data: dict[str, Any] | None = None


class RecordTransitionRead(BaseModel):
    id: str
    label: str
    to: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)


class RecordDependencyCreate(BaseModel):
    actor_user_id: UUID
    predecessor_id: UUID
    successor_id: UUID
    dependency_type: str = "finish_to_start"


class RecordDependencyRead(BaseModel):
    id: UUID
    project_id: UUID
    predecessor_id: UUID
    successor_id: UUID
    dependency_type: str

    model_config = {"from_attributes": True}


class RecordTypeRead(BaseModel):
    key: str
    label: str
    storage: str
    field_schema: list[dict[str, Any]] = Field(default_factory=list)
    parent_types: list[str] = Field(default_factory=list)
    orden: int = 0
