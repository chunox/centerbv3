"""Validación de project_records.data contra field definitions."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ProjectFieldDefinition, ProjectRecord


def list_field_defs(
    db: Session, project_id: uuid.UUID, entity_type_key: str
) -> list[ProjectFieldDefinition]:
    return list(
        db.scalars(
            select(ProjectFieldDefinition)
            .where(
                ProjectFieldDefinition.project_id == project_id,
                ProjectFieldDefinition.entity_type_key == entity_type_key,
            )
            .order_by(ProjectFieldDefinition.orden.asc())
        )
    )


def validate_record_data(
    db: Session,
    project_id: uuid.UUID,
    entity_type_key: str,
    data: dict[str, Any],
    *,
    partial: bool = False,
) -> dict[str, Any]:
    defs = list_field_defs(db, project_id, entity_type_key)
    if not defs:
        return data

    out = dict(data)
    for fd in defs:
        key = fd.field_key
        value = out.get(key)
        config = fd.config or {}
        if value is None:
            if config.get("default") is not None and not partial:
                out[key] = config["default"]
            elif config.get("required") and not partial:
                raise HTTPException(
                    status_code=422,
                    detail=f"Campo requerido: {fd.label}",
                )
            continue
        if fd.field_type == "select" and value not in (config.get("options") or []):
            if config.get("options"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Valor inválido para {fd.label}",
                )
        if fd.field_type == "multi_select":
            if not isinstance(value, list):
                raise HTTPException(
                    status_code=422,
                    detail=f"{fd.label} debe ser una lista",
                )
            opts = config.get("options") or []
            if opts:
                invalid = [v for v in value if v not in opts]
                if invalid:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Valor inválido para {fd.label}",
                    )
        if fd.field_type == "number" and value is not None:
            try:
                out[key] = int(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"{fd.label} debe ser numérico"
                ) from exc
        if fd.field_type == "checkbox":
            out[key] = bool(value)
    return out


def apply_validated_data(
    db: Session, record: ProjectRecord, data: dict[str, Any], *, partial: bool = False
) -> None:
    validated = validate_record_data(
        db, record.project_id, record.record_type, data, partial=partial
    )
    current = record.data if isinstance(record.data, dict) else {}
    merged = dict(current)
    merged.update(validated)
    record.data = merged
