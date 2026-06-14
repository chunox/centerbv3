"""Autorización por capacidades."""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.capabilities import resolve_capability_keys
from app.services.workflow.capabilities import user_has_capability

__all__ = ["assert_capability", "assert_any_capability", "resolve_capability_keys"]


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
    if any(
        user_has_capability(db, project_id, user_id, cap) for cap in capabilities
    ):
        return
    raise HTTPException(
        status_code=403,
        detail=detail or "Sin permisos suficientes",
    )
