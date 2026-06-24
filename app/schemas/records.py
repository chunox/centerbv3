"""Schemas de records — request y response."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ─── Response ────────────────────────────────────────────────────────────────

class AssigneeResponse(BaseModel):
    user_id: str
    nombre: str
    avatar_url: str | None = None


class BlockerResponse(BaseModel):
    id: str
    description: str
    created_by: str
    created_at: datetime


class RecordResponse(BaseModel):
    id: str
    project_id: str
    record_type: str
    parent_id: str | None = None
    orden: int
    title: str
    descripcion: str | None = None
    status: str
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    estimacion: float | None = None
    extra: dict[str, Any]
    assignees: list[AssigneeResponse]
    active_blockers: list[BlockerResponse]
    is_blocked: bool = False
    has_unsatisfied_dependencies: bool = False
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecordListResponse(BaseModel):
    items: list[RecordResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


# ─── Requests ────────────────────────────────────────────────────────────────

class CreateRecordRequest(BaseModel):
    record_type: str
    title: str = Field(min_length=1, max_length=500)
    parent_id: str | None = None
    orden: int = 0
    descripcion: str | None = None
    status: str | None = None          # si None se usa initial_state del workflow
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    estimacion: float | None = None
    extra: dict[str, Any] = {}
    assignee_ids: list[str] = []

    @field_validator("record_type")
    @classmethod
    def validate_record_type(cls, v: str) -> str:
        valid = {"milestone", "feature", "task", "sprint", "product_backlog"}
        if v not in valid:
            raise ValueError(f"record_type inválido: {v}. Válidos: {valid}")
        return v


class UpdateRecordRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    descripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    estimacion: float | None = None
    extra: dict[str, Any] | None = None
    orden: int | None = None
    assignee_ids: list[str] | None = None


class TransitionRequest(BaseModel):
    action_id: str


class ReorderRequest(BaseModel):
    ordered_ids: list[str]    # IDs en el nuevo orden
