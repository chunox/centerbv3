"""Mapeo ProjectRecord → RecordRead genérico."""
from __future__ import annotations

import uuid

from app.models.entities import ProjectRecord
from app.schemas.records import RecordRead
from app.services.records.repository import _data


def record_to_read(row: ProjectRecord, assignee_ids: list[uuid.UUID] | None = None) -> RecordRead:
    d = _data(row)
    return RecordRead(
        id=row.id,
        project_id=row.project_id,
        record_type=row.record_type,
        titulo=row.titulo,
        descripcion=row.descripcion,
        estado=row.estado,
        parent_id=row.parent_id,
        data=d,
        fecha_inicio=row.fecha_inicio,
        fecha_fin=row.fecha_fin,
        orden=row.orden,
        assignee_ids=assignee_ids or sorted(a.user_id for a in row.assignees),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
