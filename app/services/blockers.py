"""
Bloqueantes — cascada derivada en runtime (MVP1 §8.8).

Un record está bloqueado si él o cualquier ancestro tiene un bloqueante activo.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord, ProjectRecordBlocker, ProjectRecordDependency

DONE_PREDECESSOR_STATES = frozenset({"completado", "completed", "cancel", "cancelado"})


def _ancestor_ids(db: Session, record: ProjectRecord) -> list[str]:
    """IDs del record y todos sus ancestros (record → parent → …)."""
    ids: list[str] = [str(record.id)]
    current_id = record.parent_id
    seen: set[str] = {str(record.id)}
    while current_id:
        cid = str(current_id)
        if cid in seen:
            break
        seen.add(cid)
        ids.append(cid)
        parent = (
            db.query(ProjectRecord.parent_id)
            .filter(ProjectRecord.id == cid)
            .first()
        )
        current_id = parent[0] if parent else None
    return ids


def has_active_blocker_on_chain(db: Session, record: ProjectRecord) -> bool:
    """True si el record o algún ancestro tiene bloqueante activo."""
    chain_ids = _ancestor_ids(db, record)
    if not chain_ids:
        return False
    return (
        db.query(ProjectRecordBlocker.id)
        .filter(
            ProjectRecordBlocker.record_id.in_(chain_ids),
            ProjectRecordBlocker.resolved_at.is_(None),
        )
        .first()
        is not None
    )


def get_blocking_ancestor_id(db: Session, record: ProjectRecord) -> str | None:
    """ID del ancestro más cercano con bloqueante activo (incluye el propio record)."""
    for rid in _ancestor_ids(db, record):
        blocker = (
            db.query(ProjectRecordBlocker)
            .filter(
                ProjectRecordBlocker.record_id == rid,
                ProjectRecordBlocker.resolved_at.is_(None),
            )
            .first()
        )
        if blocker:
            return rid
    return None


def has_unsatisfied_dependencies(db: Session, record: ProjectRecord) -> bool:
    """True si algún predecessor no está en estado terminal."""
    unsatisfied = (
        db.query(ProjectRecordDependency.id)
        .join(
            ProjectRecord,
            ProjectRecord.id == ProjectRecordDependency.predecessor_id,
        )
        .filter(
            ProjectRecordDependency.successor_id == record.id,
            ProjectRecord.status.notin_(list(DONE_PREDECESSOR_STATES)),
        )
        .first()
    )
    return unsatisfied is not None
