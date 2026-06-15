"""Esquema Pydantic del manifest de Project Pack."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ViewType = Literal[
    "board",
    "gantt",
    "timeline",
    "checklist",
    "inbox",
    "custom",
    "team",
    "activity",
    "studio",
    "settings",
    "hub",
]
FieldType = Literal[
    "text",
    "textarea",
    "number",
    "date",
    "datetime",
    "select",
    "multi_select",
    "user",
    "checkbox",
    "url",
    "file",
    "relation",
]


class FieldDef(BaseModel):
    id: str
    label: str
    type: FieldType = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    indexed: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class FieldDefinitionDef(BaseModel):
    """Campo de entity type (tabla project_field_definitions)."""
    entity_type_key: str
    field_key: str
    label: str
    field_type: FieldType = "text"
    config: dict[str, Any] = Field(default_factory=dict)
    orden: int = 0
    is_system: bool = True


class EntityTypeDef(BaseModel):
    key: str
    label: str
    hierarchy: Literal["root", "child"] = "root"
    parent_of: list[str] = Field(default_factory=list)
    parent_type: str | None = None
    parent_type_keys: list[str] = Field(default_factory=list)
    fields: list[FieldDef] = Field(default_factory=list)
    traits: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = None
    is_system: bool = True
    orden: int = 0


class BlockDef(BaseModel):
    block_slug: str
    key: str
    label: str
    config: dict[str, Any] = Field(default_factory=dict)
    orden: int = 0


class ViewDef(BaseModel):
    key: str
    label: str
    route: str
    icon: str = "circle"
    section: str = "plan"
    layout: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    orden: int = 0
    # Legacy compat for workbench derivation
    view_type: ViewType = "custom"
    entity_type: str | None = None
    queue_filter: dict[str, Any] | None = None


class PackViewDef(BaseModel):
    key: str
    type: ViewType
    label: str = ""
    entity_type: str | None = None
    entity_types: list[str] = Field(default_factory=list)
    workbench_key: str | None = None


class PackRoleDef(BaseModel):
    slug: str
    nombre: str
    capabilities: list[str] = Field(default_factory=list)
    is_system: bool = True
    orden: int = 0
    template_slugs: list[str] = Field(default_factory=list)


class PackWorkbenchDef(BaseModel):
    key: str
    label: str
    route: str
    icon: str = "circle"
    section: str = "plan"
    view_type: ViewType = "custom"
    entity_type: str | None = None
    custom_view_key: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    queue_filter: dict[str, Any] | None = None
    orden: int = 0


class PackManifest(BaseModel):
    slug: str
    nombre: str
    descripcion: str = ""
    traits: dict[str, Any] = Field(default_factory=dict)
    entity_types: list[EntityTypeDef] = Field(default_factory=list)
    field_definitions: list[FieldDefinitionDef] = Field(default_factory=list)
    views: list[PackViewDef] = Field(default_factory=list)
    workflows: dict[str, dict[str, Any]] = Field(default_factory=dict)
    workflow_profiles: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    workflow_variants: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    roles: list[PackRoleDef] = Field(default_factory=list)
    workbenches: list[PackWorkbenchDef] = Field(default_factory=list)
    blocks: list[BlockDef] = Field(default_factory=list)
    project_views: list[ViewDef] = Field(default_factory=list)
    communication_rules: list[dict[str, Any]] = Field(default_factory=list)
    maps_template_slug: str | None = None
