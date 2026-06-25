"""
Bloqueantes — cascada derivada en runtime (MVP1 §8.8).

Un record está bloqueado si él o cualquier ancestro tiene un bloqueante activo.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord, ProjectRecordBlocker, ProjectRecordDependency

DONE_PREDECESSOR_STATES = frozenset({"done", "cancelled"})


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


from app.services.blockers.sync import (  # noqa: E402
    apply_block_to_record,
    cascade_block_to_descendants,
    cascade_unblock_inherited,
    clear_blockers_on_record,
    has_blocked_descendant,
    has_own_active_blocker,
    restore_record_after_unblock,
    sync_block_on_create,
    sync_unblock_on_resolve,
)

__all__ = [
    "DONE_PREDECESSOR_STATES",
    "has_active_blocker_on_chain",
    "get_blocking_ancestor_id",
    "has_unsatisfied_dependencies",
    "has_own_active_blocker",
    "has_blocked_descendant",
    "apply_block_to_record",
    "restore_record_after_unblock",
    "cascade_block_to_descendants",
    "cascade_unblock_inherited",
    "clear_blockers_on_record",
    "sync_block_on_create",
    "sync_unblock_on_resolve",
]
