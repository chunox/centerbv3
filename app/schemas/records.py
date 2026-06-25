"""Schemas de records — request y response."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    sprint_id: str | None = None
    in_product_backlog: bool = False
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
    cascade: Literal["none", "all"] = "none"
    cascade_mode: Literal[
        "none", "all", "movable_only", "movable_and_cancel_rest", "cancel_misaligned_stories",
    ] = "none"
    sprint_id: str | None = None
    reopen_children: bool = False
    cancel_children: Literal["none", "all"] = "none"
    children_on_return: Literal["unchanged", "return_to_backlog", "cancel"] = "return_to_backlog"
    skip_blocked: bool | None = Field(
        default=None,
        description="Deprecado — rechazado si true",
    )

    @model_validator(mode="after")
    def reject_deprecated_skip_blocked(self) -> TransitionRequest:
        if self.skip_blocked is True:
            raise ValueError(
                "skip_blocked está deprecado y ya no tiene efecto; resuelve los bloqueos antes de cascadar."
            )
        return self


class TransitionPreviewRequest(BaseModel):
    action_id: str
    sprint_id: str | None = None


class CascadeChildPreview(BaseModel):
    id: str
    title: str
    entity_type: str
    scrum_role: str
    from_status: str
    to_status: str
    action_id: str | None = None
    can_transition: bool
    is_blocked: bool
    reason: str | None = None


class MisalignedStoryPreview(BaseModel):
    id: str
    title: str
    status: str


class CascadePreviewResponse(BaseModel):
    record_id: str
    title: str
    entity_type: str
    scrum_role: str
    from_status: str
    to_status: str
    action_id: str
    children: list[CascadeChildPreview]
    requires_confirmation: bool
    requires_sprint_assignment: bool = False
    active_sprint_id: str | None = None
    epic_done_blocked: bool = False
    stories_misaligned: list[MisalignedStoryPreview] = []
    blocked_in_chain: bool = False
    children_ahead: list[CascadeChildPreview] = []
    epic_done_misaligned: bool = False
    cascade_modes_available: list[str] = []


class ReorderRequest(BaseModel):
    ordered_ids: list[str]    # IDs en el nuevo orden
