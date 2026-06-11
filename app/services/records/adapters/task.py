from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.records.types import RecordDTO
from app.models.entities import Task
from app.services.records.adapters.base import LegacyRecordAdapter


class TaskAdapter(LegacyRecordAdapter):
    record_type = "task"
    audit_entidad_tipo = "tarea"

    def get_entity(self, db: Session, record_id: uuid.UUID) -> Task | None:
        return db.get(Task, record_id)

    def get(self, db: Session, record_id: uuid.UUID) -> RecordDTO | None:
        row = self.get_entity(db, record_id)
        if row is None:
            return None
        return RecordDTO(
            id=row.id,
            project_id=row.project_id,
            record_type=self.record_type,
            storage="legacy",
            titulo=row.titulo,
            descripcion=row.descripcion,
            estado=row.estado,
            parent_id=row.feature_id,
            data={"feature_id": str(row.feature_id), "parent_task_id": str(row.parent_task_id) if row.parent_task_id else None},
            fecha_inicio=None,
            fecha_fin=None,
            orden=0,
            assignee_ids=row.asignado_ids,
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
        stmt = select(Task).where(Task.project_id == project_id)
        if parent_id is not None:
            stmt = stmt.where(Task.feature_id == parent_id)
        return [self.get(db, t.id) for t in db.scalars(stmt) if self.get(db, t.id)]
