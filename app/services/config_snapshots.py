"""Snapshots de configuración Studio."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectConfigSnapshot

ConfigKind = Literal["workflows", "communication", "workbenches"]


def save_config_snapshot(
    db: Session,
    project: Project,
    *,
    kind: ConfigKind,
    payload: Any,
    created_by: uuid.UUID | None,
) -> ProjectConfigSnapshot:
    row = ProjectConfigSnapshot(
        project_id=project.id,
        kind=kind,
        payload=payload,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    _trim_snapshots(db, project.id, kind, keep=10)
    return row


def _trim_snapshots(
    db: Session,
    project_id: uuid.UUID,
    kind: str,
    *,
    keep: int,
) -> None:
    rows = list(
        db.scalars(
            select(ProjectConfigSnapshot)
            .where(
                ProjectConfigSnapshot.project_id == project_id,
                ProjectConfigSnapshot.kind == kind,
            )
            .order_by(ProjectConfigSnapshot.created_at.desc())
        )
    )
    for row in rows[keep:]:
        db.delete(row)


def list_config_snapshots(
    db: Session,
    project_id: uuid.UUID,
    *,
    kind: ConfigKind | None = None,
    limit: int = 10,
) -> list[ProjectConfigSnapshot]:
    stmt = select(ProjectConfigSnapshot).where(
        ProjectConfigSnapshot.project_id == project_id
    )
    if kind:
        stmt = stmt.where(ProjectConfigSnapshot.kind == kind)
    stmt = stmt.order_by(ProjectConfigSnapshot.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))
