"""Autorización por capacidades."""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.capabilities import resolve_capability_keys
from app.services.workflow.capabilities import get_effective_capabilities, user_has_capability


def assert_capability(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    capability: str,
    *,
    detail: str | None = None,
) -> None:
    if not user_has_capability(db, project_id, user_id, capability):
        raise HTTPException(
            status_code=403,
            detail=detail or f"Se requiere capacidad '{capability}'",
        )


def assert_any_capability(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    capabilities: list[str],
    *,
    detail: str | None = None,
) -> None:
    effective = get_effective_capabilities(db, project_id, user_id)
    expanded = resolve_capability_keys(capabilities)
    if not any(c in effective for c in expanded):
        raise HTTPException(
            status_code=403,
            detail=detail or "Sin permisos suficientes",
        )
