"""Adaptador base para entidades legacy."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from app.domain.records.types import RecordDTO, RecordRef, StorageKind


class LegacyRecordAdapter(ABC):
    record_type: str
    storage: StorageKind = "legacy"
    audit_entidad_tipo: str

    @abstractmethod
    def get(self, db: Session, record_id: uuid.UUID) -> RecordDTO | None: ...

    @abstractmethod
    def get_entity(self, db: Session, record_id: uuid.UUID) -> Any | None:
        """ORM entity para workflow engine."""
        ...

    @abstractmethod
    def list(
        self,
        db: Session,
        project_id: uuid.UUID,
        *,
        parent_id: uuid.UUID | None = None,
        record_type: str | None = None,
    ) -> list[RecordDTO]: ...

    def to_ref(self, dto: RecordDTO) -> RecordRef:
        return RecordRef(
            id=dto.id,
            record_type=dto.record_type,
            storage=dto.storage,
            project_id=dto.project_id,
        )

    def resolve_project_id(self, db: Session, record_id: uuid.UUID) -> uuid.UUID | None:
        dto = self.get(db, record_id)
        return dto.project_id if dto else None
