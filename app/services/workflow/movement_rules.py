"""Reglas globales de movimiento con bloqueos (SCRUM_KANBAN_MOVEMENTS § regla global)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord
from app.services.blockers import has_blocked_descendant
from app.services.workflow.errors import WorkflowError

BLOCK_EXEMPT_ACTIONS = frozenset({"devolver", "cancel", "cancelar"})


def assert_movement_allowed(db: Session, record: ProjectRecord, action_id: str) -> None:
    """Bloquea transiciones si el record o un descendiente está en status=blocked."""
    if action_id in BLOCK_EXEMPT_ACTIONS:
        return
    if record.status == "blocked":
        raise WorkflowError(
            "El record está bloqueado. Resuelve el bloqueo antes de mover o usa cancelar/devolver."
        )
    if has_blocked_descendant(db, record):
        raise WorkflowError(
            "No se puede mover: hay descendientes en estado bloqueado. Resuelve los bloqueos primero."
        )
