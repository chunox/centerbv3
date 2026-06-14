"""Schemas para vista Equipo PM (asignaciones por miembro)."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TeamAssignableTypeRead(BaseModel):
    key: str
    label: str


class TeamAssignmentRead(BaseModel):
    record_id: UUID
    record_type: str
    record_type_label: str
    titulo: str
    estado: str
    estado_label: str
    badge: str
    category: str | None = None
    is_terminal: bool = False
    parent_id: UUID | None = None
    parent_titulo: str | None = None
    root_parent_id: UUID | None = None
    root_parent_titulo: str | None = None
    project_id: UUID | None = None
    project_nombre: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    updated_at: datetime | None = None
    workbench_route: str | None = None
    view_route: str | None = None


class TeamFeatureScheduleRead(BaseModel):
    feature_id: UUID
    titulo: str
    root_parent_titulo: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    active_tasks: int = 0
    assignee_names: list[str] = Field(default_factory=list)


class TeamMemberSummaryRead(BaseModel):
    total: int = 0
    active: int = 0
    done: int = 0
    terminal: int = 0


class TeamMemberBoardRead(BaseModel):
    user_id: UUID
    nombre: str
    email: str | None = None
    role_slugs: list[str] = Field(default_factory=list)
    role_labels: list[str] = Field(default_factory=list)
    summary: TeamMemberSummaryRead = Field(default_factory=TeamMemberSummaryRead)
    items: list[TeamAssignmentRead] = Field(default_factory=list)


class TeamBoardTotalsRead(BaseModel):
    members: int = 0
    assignments: int = 0
    active: int = 0
    done: int = 0
    unassigned: int = 0


class TeamBoardRead(BaseModel):
    assignable_types: list[TeamAssignableTypeRead] = Field(default_factory=list)
    members: list[TeamMemberBoardRead] = Field(default_factory=list)
    unassigned: list[TeamAssignmentRead] = Field(default_factory=list)
    feature_schedules: list[TeamFeatureScheduleRead] = Field(default_factory=list)
    totals: TeamBoardTotalsRead = Field(default_factory=TeamBoardTotalsRead)
