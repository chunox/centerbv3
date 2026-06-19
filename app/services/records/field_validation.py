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
        return _enforce_task_hour_fields(entity_type_key, data)

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
                if config.get("allow_decimal"):
                    parsed = float(value)
                    step = float(config.get("step") or 0.5)
                    min_val = float(config.get("min") if config.get("min") is not None else 0)
                    if parsed < min_val:
                        raise HTTPException(
                            status_code=422,
                            detail=f"{fd.label} debe ser >= {min_val}",
                        )
                    remainder = round(parsed / step) * step - parsed
                    if abs(remainder) > 1e-9:
                        raise HTTPException(
                            status_code=422,
                            detail=f"{fd.label} debe ser múltiplo de {step}",
                        )
                    out[key] = round(parsed * 2) / 2 if step == 0.5 else parsed
                else:
                    out[key] = int(value)
            except HTTPException:
                raise
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"{fd.label} debe ser numérico"
                ) from exc
        if fd.field_type == "checkbox":
            out[key] = bool(value)
    return _enforce_task_hour_fields(entity_type_key, out)


def _enforce_task_hour_fields(
    entity_type_key: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Salvaguarda estimacion_horas aunque falte field definition en el proyecto."""
    if entity_type_key != "task" or "estimacion_horas" not in data:
        return data
    value = data.get("estimacion_horas")
    if value is None or value == "":
        return data
    out = dict(data)
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail="Estimación (h) debe ser numérico"
        ) from exc
    if parsed < 0:
        raise HTTPException(
            status_code=422, detail="Estimación (h) debe ser >= 0"
        )
    out["estimacion_horas"] = parsed
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
