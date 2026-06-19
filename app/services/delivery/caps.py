"""Helpers de autorización compartidos por delivery services."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.capabilities import PROJECT_ROLES_MANAGE
from app.services.workflow.authorize import assert_capability
from app.services.workflow.capabilities import user_has_capability


def assert_record_cap(db: Session, project_id: UUID, user_id: UUID, cap: str) -> None:
    if user_has_capability(db, project_id, user_id, cap):
        return
    if user_has_capability(db, project_id, user_id, PROJECT_ROLES_MANAGE):
        return
    assert_capability(db, project_id, user_id, cap)
