"""Registro de tipos de registro y resolución de project_id."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.packs.catalog import LEGACY_ENTITY_TYPES
from app.domain.records.types import RecordDTO, RecordRef
from app.models.entities import ProjectRecord, ProjectRecordType
from app.services.records.adapters import LEGACY_ADAPTERS
from app.services.records.adapters.base import LegacyRecordAdapter
from app.services.records import generic_store


class RecordTypeRegistry:
    def get_adapter(self, record_type: str) -> LegacyRecordAdapter | None:
        return LEGACY_ADAPTERS.get(record_type)

    def is_legacy(self, record_type: str) -> bool:
        return record_type in LEGACY_ADAPTERS

    def audit_entidad_tipo(self, record_type: str) -> str:
        adapter = LEGACY_ADAPTERS.get(record_type)
        if adapter:
            return adapter.audit_entidad_tipo
        return record_type

    def workflow_entity_types_for_project(
        self, db: Session, project_id: uuid.UUID
    ) -> list[str]:
        types = list(
            db.scalars(
                select(ProjectRecordType.key).where(
                    ProjectRecordType.project_id == project_id
                )
            )
        )
        if types:
            return types
        return list(LEGACY_ENTITY_TYPES)

    def get(
        self, db: Session, record_ref: RecordRef
    ) -> tuple[RecordDTO | None, object | None]:
        """Retorna (dto, entity_or_row) para workflow."""
        if record_ref.storage == "legacy":
            adapter = self.get_adapter(record_ref.record_type)
            if adapter is None:
                return None, None
            dto = adapter.get(db, record_ref.id)
            entity = adapter.get_entity(db, record_ref.id) if dto else None
            return dto, entity
        row = generic_store.get_record_entity(db, record_ref.id)
        dto = generic_store.get_record(db, record_ref.id) if row else None
        return dto, row

    def resolve_ref(
        self, db: Session, record_type: str, record_id: uuid.UUID
    ) -> RecordRef | None:
        adapter = self.get_adapter(record_type)
        if adapter:
            dto = adapter.get(db, record_id)
            if dto is None:
                return None
            return RecordRef(
                id=dto.id,
                record_type=record_type,
                storage="legacy",
                project_id=dto.project_id,
            )
        row = db.get(ProjectRecord, record_id)
        if row is None:
            return None
        return RecordRef(
            id=row.id,
            record_type=row.record_type,
            storage="generic",
            project_id=row.project_id,
        )

    def resolve_project_id(
        self, db: Session, entidad_tipo: str, entidad_id: uuid.UUID
    ) -> uuid.UUID | None:
        legacy_map = {a.audit_entidad_tipo: rt for rt, a in LEGACY_ADAPTERS.items()}
        legacy_map.update({rt: rt for rt in LEGACY_ADAPTERS})
        record_type = legacy_map.get(entidad_tipo, entidad_tipo)
        adapter = self.get_adapter(record_type)
        if adapter:
            return adapter.resolve_project_id(db, entidad_id)
        row = db.get(ProjectRecord, entidad_id)
        return row.project_id if row else None

    def list_records(
        self,
        db: Session,
        project_id: uuid.UUID,
        *,
        record_type: str,
        parent_id: uuid.UUID | None = None,
    ) -> list[RecordDTO]:
        if self.is_legacy(record_type):
            adapter = self.get_adapter(record_type)
            assert adapter is not None
            return adapter.list(db, project_id, parent_id=parent_id, record_type=record_type)
        return generic_store.list_records(
            db, project_id, record_type=record_type, parent_id=parent_id
        )


registry = RecordTypeRegistry()
