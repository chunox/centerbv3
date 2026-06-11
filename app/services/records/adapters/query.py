from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.records.types import RecordDTO
from app.models.entities import FeatureQuery
from app.services.records.adapters.base import LegacyRecordAdapter


class QueryAdapter(LegacyRecordAdapter):
    record_type = "query"
    audit_entidad_tipo = "feature_query"

    def get_entity(self, db: Session, record_id: uuid.UUID) -> FeatureQuery | None:
        return db.get(FeatureQuery, record_id)

    def get(self, db: Session, record_id: uuid.UUID) -> RecordDTO | None:
        row = self.get_entity(db, record_id)
        if row is None:
            return None
        project_id = row.feature.project_id if row.feature else None
        if project_id is None:
            return None
        return RecordDTO(
            id=row.id,
            project_id=project_id,
            record_type=self.record_type,
            storage="legacy",
            titulo=row.titulo,
            descripcion=row.descripcion,
            estado=row.estado,
            parent_id=row.feature_id,
            data={"feature_id": str(row.feature_id)},
            fecha_inicio=None,
            fecha_fin=None,
            orden=0,
            assignee_ids=[],
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def list(
        self,
        db: Session,
        project_id: uuid.UUID,
        *,
        parent_id: uuid.UUID | None = None,
        record_type: str | None = None,
    ) -> list[RecordDTO]:
        from app.models.entities import Feature

        stmt = (
            select(FeatureQuery)
            .join(Feature, Feature.id == FeatureQuery.feature_id)
            .where(Feature.project_id == project_id)
        )
        if parent_id is not None:
            stmt = stmt.where(FeatureQuery.feature_id == parent_id)
        return [dto for q in db.scalars(stmt) if (dto := self.get(db, q.id))]
