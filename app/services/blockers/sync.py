"""
Sincronización status=blocked ↔ project_record_blockers.

Ver docs/SCRUM_KANBAN_MOVEMENTS.md § Estado blocked.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.scrum.states import (
    EXTRA_BLOCKED_BY_INHERITANCE,
    EXTRA_STATUS_BEFORE_BLOCK,
    SCRUM_TERMINAL_STATES,
)
from app.models.entities import ProjectRecord, ProjectRecordBlocker
from app.services.scrum.descendants import collect_scrum_descendants


def has_own_active_blocker(db: Session, record: ProjectRecord) -> bool:
    return (
        db.query(ProjectRecordBlocker.id)
        .filter(
            ProjectRecordBlocker.record_id == str(record.id),
            ProjectRecordBlocker.resolved_at.is_(None),
        )
        .first()
        is not None
    )


def _children(db: Session, parent_id: str, project_id: str) -> list[ProjectRecord]:
    return (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.parent_id == parent_id,
            ProjectRecord.project_id == project_id,
        )
        .all()
    )


def _descendants_bfs(db: Session, root_id: str, project_id: str) -> list[ProjectRecord]:
    result: list[ProjectRecord] = []
    queue = [root_id]
    seen: set[str] = set()
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        for child in _children(db, pid, project_id):
            result.append(child)
            queue.append(str(child.id))
    return result


def has_blocked_descendant(db: Session, record: ProjectRecord) -> bool:
    """True si algún descendiente tiene status=blocked (regla global padre)."""
    role = (record.extra or {}).get("scrum_role")
    if role in ("epic", "story", "dev"):
        descendants = collect_scrum_descendants(db, record, str(record.project_id))
    else:
        descendants = _descendants_bfs(db, str(record.id), str(record.project_id))
    return any(d.status == "blocked" for d in descendants)


def apply_block_to_record(record: ProjectRecord, *, inherited: bool = False) -> bool:
    """Pasa el record a status=blocked. Retorna True si cambió el status."""
    if record.status in SCRUM_TERMINAL_STATES:
        return False

    extra = dict(record.extra or {})

    if record.status == "blocked":
        if inherited:
            extra[EXTRA_BLOCKED_BY_INHERITANCE] = True
            record.extra = extra
        return False

    extra[EXTRA_STATUS_BEFORE_BLOCK] = record.status
    if inherited:
        extra[EXTRA_BLOCKED_BY_INHERITANCE] = True
    else:
        extra.pop(EXTRA_BLOCKED_BY_INHERITANCE, None)
    record.extra = extra
    record.status = "blocked"
    return True


def restore_record_after_unblock(db: Session, record: ProjectRecord) -> bool:
    """Restaura status_before_block si ya no hay bloqueo activo en la cadena."""
    from app.services.blockers import has_active_blocker_on_chain

    if record.status != "blocked":
        return False

    if has_own_active_blocker(db, record):
        return False

    if has_active_blocker_on_chain(db, record):
        extra = dict(record.extra or {})
        extra[EXTRA_BLOCKED_BY_INHERITANCE] = True
        record.extra = extra
        return False

    extra = dict(record.extra or {})
    prev = extra.pop(EXTRA_STATUS_BEFORE_BLOCK, None) or "backlog"
    extra.pop(EXTRA_BLOCKED_BY_INHERITANCE, None)
    record.extra = extra

    if prev in SCRUM_TERMINAL_STATES:
        record.status = "backlog"
    else:
        record.status = prev
    return True


def cascade_block_to_descendants(
    db: Session,
    project_id: str,
    root_id: str,
) -> list[ProjectRecord]:
    changed: list[ProjectRecord] = []
    for desc in _descendants_bfs(db, root_id, project_id):
        if desc.status in SCRUM_TERMINAL_STATES:
            continue
        if has_own_active_blocker(db, desc):
            continue
        if apply_block_to_record(desc, inherited=True):
            changed.append(desc)
    return changed


def cascade_unblock_inherited(db: Session, project_id: str, root_id: str) -> None:
    for desc in _descendants_bfs(db, root_id, project_id):
        extra = desc.extra or {}
        if not extra.get(EXTRA_BLOCKED_BY_INHERITANCE):
            continue
        restore_record_after_unblock(db, desc)


def clear_blockers_on_record(db: Session, record_id: str, *, resolved_by: str | None = None) -> int:
    blockers = (
        db.query(ProjectRecordBlocker)
        .filter(
            ProjectRecordBlocker.record_id == record_id,
            ProjectRecordBlocker.resolved_at.is_(None),
        )
        .all()
    )
    now = datetime.now(timezone.utc)
    for blocker in blockers:
        blocker.resolved_at = now
        if resolved_by:
            blocker.resolved_by = resolved_by
    return len(blockers)


def sync_block_on_create(db: Session, record: ProjectRecord) -> list[ProjectRecord]:
    """Tras crear el primer bloqueante: bloquear record + cascada a descendientes."""
    if not has_own_active_blocker(db, record):
        return []

    changed: list[ProjectRecord] = []
    if record.status != "blocked":
        if apply_block_to_record(record, inherited=False):
            changed.append(record)
    changed.extend(
        cascade_block_to_descendants(db, str(record.project_id), str(record.id))
    )
    return changed


def sync_unblock_on_resolve(db: Session, record: ProjectRecord) -> None:
    """Tras resolver un bloqueante: restaurar record y descendientes heredados."""
    restore_record_after_unblock(db, record)
    cascade_unblock_inherited(db, str(record.project_id), str(record.id))
