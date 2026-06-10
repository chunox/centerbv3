from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CapabilityDefRead(BaseModel):
    key: str
    label: str
    group: str
    description: str = ""


class ProjectRoleRead(BaseModel):
    id: UUID
    project_id: UUID
    slug: str
    nombre: str
    descripcion: str | None = None
    color: str | None = None
    is_system: bool
    orden: int
    capabilities: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class WorkbenchRead(BaseModel):
    key: str
    label: str
    route: str
    icon: str = "circle"
    section: str = "plan"
    required_capabilities: list[str] = Field(default_factory=list)
    queue_filter: dict[str, Any] | None = None
    orden: int = 0


class WorkflowSummaryRead(BaseModel):
    entity_type: str
    version: int
    states: list[dict[str, Any]]
    transitions: list[dict[str, Any]]
    initial_state: str | None = None
    terminal_states: list[str] = Field(default_factory=list)


class ProjectAccessContextRead(BaseModel):
    user_id: UUID
    roles: list[ProjectRoleRead]
    capabilities: list[str]
    workflows: dict[str, WorkflowSummaryRead]
    workbenches: list[WorkbenchRead]
    capability_catalog: list[CapabilityDefRead] = Field(default_factory=list)


class ProjectRoleCreate(BaseModel):
    actor_user_id: UUID
    slug: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str | None = None
    color: str | None = None
    capability_keys: list[str] = Field(default_factory=list)


class ProjectRoleCapabilitiesUpdate(BaseModel):
    actor_user_id: UUID
    capability_keys: list[str]


class ProjectWorkflowUpdate(BaseModel):
    actor_user_id: UUID
    definition: dict[str, Any]


class WorkflowTemplateApply(BaseModel):
    actor_user_id: UUID
    project_tipo: str | None = None


class ProjectWorkbenchesUpdate(BaseModel):
    actor_user_id: UUID
    workbenches: list[dict[str, Any]]
