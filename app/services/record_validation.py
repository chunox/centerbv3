"""Validación de entidades de auditoría/notificaciones vía project_records."""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord

AUDIT_RECORD_TYPE: dict[str, str] = {
    "feature": "feature",
    "tarea": "task",
    "milestone": "milestone",
    "feature_query": "query",
    "feature_report": "report",
}


def assert_project_record(
    db: Session,
    *,
    record_id: uuid.UUID,
    project_id: uuid.UUID,
    record_type: str,
    detail: str,
) -> ProjectRecord:
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project_id or row.record_type != record_type:
        raise HTTPException(status_code=404, detail=detail)
    return row
