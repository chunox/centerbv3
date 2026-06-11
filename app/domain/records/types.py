"""Tipos del dominio de registros genéricos."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

StorageKind = Literal["generic", "legacy"]


@dataclass(frozen=True, slots=True)
class RecordRef:
    id: uuid.UUID
    record_type: str
    storage: StorageKind
    project_id: uuid.UUID


@dataclass(slots=True)
class RecordDTO:
    id: uuid.UUID
    project_id: uuid.UUID
    record_type: str
    storage: StorageKind
    titulo: str
    descripcion: str | None
    estado: str
    parent_id: uuid.UUID | None
    data: dict[str, Any]
    fecha_inicio: date | None
    fecha_fin: date | None
    orden: int
    assignee_ids: list[uuid.UUID] = field(default_factory=list)
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def workflow_entity_type(self) -> str:
        return self.record_type
