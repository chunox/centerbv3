from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PackSummaryRead(BaseModel):
    slug: str
    nombre: str
    descripcion: str = ""
    orden: int = 0


class PackViewRead(BaseModel):
    key: str
    type: str
    label: str = ""
    entity_type: str | None = None
    entity_types: list[str] = Field(default_factory=list)
    workbench_key: str | None = None


class PackContextRead(BaseModel):
    slug: str
    nombre: str
    descripcion: str = ""
    entity_types: list[dict[str, Any]] = Field(default_factory=list)
    views: list[PackViewRead] = Field(default_factory=list)
