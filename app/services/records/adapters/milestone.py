from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.records.types import RecordDTO
from app.models.entities import Milestone
from app.services.records.adapters.base import LegacyRecordAdapter


class MilestoneAdapter(LegacyRecordAdapter):
    record_type = "milestone"
    audit_entidad_tipo = "milestone"

    def get_entity(self, db: Session, record_id: uuid.UUID) -> Milestone | None:
        return db.get(Milestone, record_id)

    def get(self, db: Session, record_id: uuid.UUID) -> RecordDTO | None:
        row = self.get_entity(db, record_id)
        if row is None:
            return None
        return RecordDTO(
            id=row.id,
            project_id=row.project_id,
            record_type=self.record_type,
            storage="legacy",
            titulo=row.nombre,
            descripcion=row.descripcion,
            estado=row.estado,
            parent_id=None,
            data={"tipo": row.tipo},
            fecha_inicio=row.fecha_inicio,
            fecha_fin=row.fecha_fin,
            orden=row.orden,
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
        stmt = select(Milestone).where(Milestone.project_id == project_id)
        return [dto for m in db.scalars(stmt) if (dto := self.get(db, m.id))]
