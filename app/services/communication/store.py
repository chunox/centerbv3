"""Persistencia de reglas de comunicación por proyecto."""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectCommunicationRules
from app.schemas.communication_rules import CommunicationRule
from app.services.communication.legacy_defaults import default_communication_rules_for_pack
from app.services.communication.validate import validate_communication_rules
from app.services.config_snapshots import save_config_snapshot


def _parse_rules(raw: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


def get_communication_rules(db: Session, project_id: uuid.UUID) -> list[CommunicationRule]:
    row = db.scalar(
        select(ProjectCommunicationRules).where(
            ProjectCommunicationRules.project_id == project_id
        )
    )
    if row is None:
        project = db.get(Project, project_id)
        pack_slug = project.pack_slug if project else None
        return default_communication_rules_for_pack(pack_slug)
    parsed = _parse_rules(row.definition)
    if not parsed:
        project = db.get(Project, project_id)
        pack_slug = project.pack_slug if project else None
        return default_communication_rules_for_pack(pack_slug)
    return [CommunicationRule.model_validate(r) for r in parsed]


def update_communication_rules(
    db: Session,
    project: Project,
    rules: list[CommunicationRule],
    *,
    actor_user_id: uuid.UUID | None = None,
) -> list[CommunicationRule]:
    validate_communication_rules(rules)
    existing = get_communication_rules(db, project.id)
    if existing:
        save_config_snapshot(
            db,
            project,
            kind="communication",
            payload=[r.model_dump() for r in existing],
            created_by=actor_user_id,
        )
    payload = json.dumps([r.model_dump() for r in rules], ensure_ascii=False)
    row = db.scalar(
        select(ProjectCommunicationRules).where(
            ProjectCommunicationRules.project_id == project.id
        )
    )
    if row is None:
        row = ProjectCommunicationRules(project_id=project.id, definition=payload)
        db.add(row)
    else:
        row.definition = payload
    db.flush()
    return rules
