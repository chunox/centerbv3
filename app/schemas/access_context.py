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
    view_type: str = "custom"
    entity_type: str | None = None
    custom_view_key: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    queue_filter: dict[str, Any] | None = None
    orden: int = 0
    nav_group: str | None = None
    nav_group_label: str | None = None
    nav_group_order: int = 0
    nav_primary: bool = True


class WorkflowSummaryRead(BaseModel):
    entity_type: str
    version: int
    states: list[dict[str, Any]]
    transitions: list[dict[str, Any]]
    initial_state: str | None = None
    terminal_states: list[str] = Field(default_factory=list)
    capabilities_added: list[str] = Field(default_factory=list)
    node_positions: dict[str, Any] | None = None


def workflow_summary_from_definition(
    entity_type: str,
    version: int,
    defn: dict[str, Any],
    *,
    capabilities_added: list[str] | None = None,
) -> WorkflowSummaryRead:
    return WorkflowSummaryRead(
        entity_type=entity_type,
        version=version,
        states=defn.get("states", []),
        transitions=defn.get("transitions", []),
        initial_state=defn.get("initial_state"),
        terminal_states=defn.get("terminal_states", []),
        capabilities_added=capabilities_added or [],
        node_positions=defn.get("node_positions"),
    )


class RecordTypeRead(BaseModel):
    key: str
    label: str
    field_schema: list[dict[str, Any]] = Field(default_factory=list)
    parent_types: list[str] = Field(default_factory=list)
    icon: str | None = None
    traits: dict[str, Any] = Field(default_factory=dict)
    is_system: bool = False
    orden: int = 0


class EntityTypeRead(RecordTypeRead):
    """Alias semántico para entity types del espacio."""


class FieldDefinitionRead(BaseModel):
    entity_type_key: str
    field_key: str
    label: str
    field_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    orden: int = 0
    is_system: bool = False


class ProjectBlockRead(BaseModel):
    key: str
    block_slug: str
    label: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    orden: int = 0


class ProjectViewRead(BaseModel):
    key: str
    label: str
    route: str
    icon: str = "circle"
    section: str = "plan"
    layout: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    orden: int = 0


class PackContextRead(BaseModel):
    slug: str
    nombre: str
    descripcion: str = ""
    views: list[dict[str, Any]] = Field(default_factory=list)


class ProjectAccessContextRead(BaseModel):
    user_id: UUID
    roles: list[ProjectRoleRead]
    capabilities: list[str]
    workflows: dict[str, WorkflowSummaryRead]
    workbenches: list[WorkbenchRead]
    capability_catalog: list[CapabilityDefRead] = Field(default_factory=list)
    pack: PackContextRead | None = None
    record_types: list[RecordTypeRead] = Field(default_factory=list)
    entity_types: list[EntityTypeRead] = Field(default_factory=list)
    field_definitions: list[FieldDefinitionRead] = Field(default_factory=list)
    blocks: list[ProjectBlockRead] = Field(default_factory=list)
    views: list[ProjectViewRead] = Field(default_factory=list)
    pack_slug: str = "software"
    template_slug: str = "default"
    project_tipo: str = "interno"
    delivery_mode: str = "waterfall"
    project_role_slugs: list[str] = Field(default_factory=list)
    member_role_slugs: list[str] = Field(default_factory=list)


class ProjectRoleCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str | None = None
    color: str | None = None
    capability_keys: list[str] = Field(default_factory=list)


class ProjectRoleCapabilitiesUpdate(BaseModel):
    capability_keys: list[str]


class ProjectWorkflowUpdate(BaseModel):
    definition: dict[str, Any]


class WorkflowTemplateApply(BaseModel):
    template_slug: str | None = None
    project_tipo: str | None = None


class ProjectWorkbenchesUpdate(BaseModel):
    workbenches: list[dict[str, Any]]
