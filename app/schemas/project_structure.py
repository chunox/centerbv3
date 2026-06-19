"""Esquemas para estructura de alcance personalizable al crear/editar proyectos."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ProjectStructureField(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)
    type: str = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)


class ProjectStructureEntity(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)
    parent_type_keys: list[str] = Field(default_factory=list)
    icon: str | None = None
    traits: dict[str, Any] = Field(default_factory=dict)
    fields: list[ProjectStructureField] = Field(default_factory=list)
    workflow: dict[str, Any] | None = None
    orden: int = 0

    @field_validator("key")
    @classmethod
    def key_slug(cls, v: str) -> str:
        cleaned = v.strip().lower().replace(" ", "_")
        if not cleaned:
            raise ValueError("key inválida")
        return cleaned


class InitialRecordDef(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    record_type: str | None = None
    descripcion: str | None = None
    orden: int = 0


class ProjectStructureDef(BaseModel):
    entity_types: list[ProjectStructureEntity] = Field(min_length=1)
    initial_roots: list[InitialRecordDef] | None = None


class EntityTypeCreate(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)
    parent_type_keys: list[str] = Field(default_factory=list)
    icon: str | None = None
    traits: dict[str, Any] = Field(default_factory=dict)
    fields: list[ProjectStructureField] = Field(default_factory=list)
    workflow: dict[str, Any] | None = None
    orden: int = 0


class EntityTypePatch(BaseModel):
    label: str | None = None
    icon: str | None = None
    traits: dict[str, Any] | None = None
    parent_type_keys: list[str] | None = None
    field_schema: list[dict[str, Any]] | None = None
    orden: int | None = None


class EntityTypeDelete(BaseModel):
    pass
