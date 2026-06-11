"""Esquema Pydantic del manifest de Project Pack."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

StorageKind = Literal["generic", "legacy"]
ViewType = Literal["board", "gantt", "timeline", "checklist", "inbox", "custom"]
FieldType = Literal[
    "text", "textarea", "number", "date", "select", "user", "checkbox", "url"
]


class FieldDef(BaseModel):
    id: str
    label: str
    type: FieldType = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)


class EntityTypeDef(BaseModel):
    key: str
    label: str
    storage: StorageKind = "generic"
    hierarchy: Literal["root", "child"] = "root"
    parent_of: list[str] = Field(default_factory=list)
    parent_type: str | None = None
    fields: list[FieldDef] = Field(default_factory=list)
    orden: int = 0


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


class PackWorkbenchDef(BaseModel):
    key: str
    label: str
    route: str
    icon: str = "circle"
    section: str = "plan"
    view_type: ViewType = "custom"
    entity_type: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    queue_filter: dict[str, Any] | None = None
    orden: int = 0


class PackManifest(BaseModel):
    slug: str
    nombre: str
    descripcion: str = ""
    entity_types: list[EntityTypeDef] = Field(default_factory=list)
    views: list[PackViewDef] = Field(default_factory=list)
    workflows: dict[str, dict[str, Any]] = Field(default_factory=dict)
    roles: list[PackRoleDef] = Field(default_factory=list)
    workbenches: list[PackWorkbenchDef] = Field(default_factory=list)
    maps_template_slug: str | None = None
