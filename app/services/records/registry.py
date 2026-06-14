"""Registro de tipos de registro y resolución de project_id."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.packs.catalog import LEGACY_ENTITY_TYPES
from app.domain.records.types import RecordDTO, RecordRef
from app.models.entities import ProjectRecord, ProjectRecordType
from app.services.records import generic_store


class RecordTypeRegistry:
    def is_legacy(self, record_type: str) -> bool:
        return False

    def audit_entidad_tipo(self, record_type: str) -> str:
        legacy_map = {
            "feature": "feature",
            "task": "tarea",
            "query": "feature_query",
            "report": "feature_report",
            "milestone": "milestone",
        }
        return legacy_map.get(record_type, record_type)

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
        row = generic_store.get_record_entity(db, record_ref.id)
        dto = generic_store.get_record(db, record_ref.id) if row else None
        return dto, row

    def resolve_ref(
        self, db: Session, record_type: str, record_id: uuid.UUID
    ) -> RecordRef | None:
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
        legacy_map = {
            "tarea": "task",
            "feature_query": "query",
            "feature_report": "report",
        }
        record_type = legacy_map.get(entidad_tipo, entidad_tipo)
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
        return generic_store.list_records(
            db, project_id, record_type=record_type, parent_id=parent_id
        )


registry = RecordTypeRegistry()
