"""
Utilidad para escribir entradas en audit_logs.
Se llama desde endpoints de transición, CRUD de records y operaciones sensibles.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import AuditLog, Project


def write_audit(
    db: Session,
    *,
    project: Project,
    actor_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    changes: dict | None = None,
) -> AuditLog:
    """
    Escribe una entrada en audit_logs y hace flush (sin commit).
    El caller es responsable de hacer commit.

    action: "created" | "updated" | "deleted" | "transitioned" | "member_added" | ...
    changes: { field: [old, new] } para updates; { "to_state": "..." } para transiciones
    """
    entry = AuditLog(
        organization_id=str(project.organization_id),
        project_id=str(project.id),
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changes=changes or {},
    )
    db.add(entry)
    db.flush()
    return entry
