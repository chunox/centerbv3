"""Servicios CRUD para sesiones y entradas de ceremonias Scrum."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ScrumCeremonyEntry, ScrumCeremonySession

SESSION_TYPES = {"daily", "planning_poker", "sprint_review", "retro"}
SESSION_STATUSES = {"planned", "active", "closed"}


def list_sessions(
    db: Session,
    project_id: uuid.UUID,
    *,
    session_type: str | None = None,
    sprint_id: uuid.UUID | None = None,
) -> list[ScrumCeremonySession]:
    stmt = (
        select(ScrumCeremonySession)
        .where(ScrumCeremonySession.project_id == project_id)
        .order_by(ScrumCeremonySession.created_at.desc())
    )
    if session_type:
        stmt = stmt.where(ScrumCeremonySession.session_type == session_type)
    if sprint_id:
        stmt = stmt.where(ScrumCeremonySession.sprint_id == sprint_id)
    return list(db.scalars(stmt))


def create_session(
    db: Session,
    *,
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    session_type: str,
    title: str,
    sprint_id: uuid.UUID | None,
    status: str = "planned",
    facilitator_user_id: uuid.UUID | None = None,
) -> ScrumCeremonySession:
    if session_type not in SESSION_TYPES:
        raise HTTPException(status_code=400, detail="session_type inválido")
    if status not in SESSION_STATUSES:
        raise HTTPException(status_code=400, detail="status inválido")
    row = ScrumCeremonySession(
        project_id=project_id,
        sprint_id=sprint_id,
        session_type=session_type,
        title=title.strip() or session_type.replace("_", " ").title(),
        status=status,
        facilitator_user_id=facilitator_user_id,
        created_by=actor_user_id,
        started_at=datetime.utcnow() if status == "active" else None,
    )
    db.add(row)
    db.flush()
    return row


def update_session(
    db: Session,
    *,
    session: ScrumCeremonySession,
    patch: dict[str, Any],
) -> ScrumCeremonySession:
    if "session_type" in patch:
        if patch["session_type"] not in SESSION_TYPES:
            raise HTTPException(status_code=400, detail="session_type inválido")
        session.session_type = patch["session_type"]
    if "title" in patch and patch["title"] is not None:
        session.title = str(patch["title"]).strip() or session.title
    if "sprint_id" in patch:
        raw = patch["sprint_id"]
        if raw in (None, ""):
            session.sprint_id = None
        else:
            session.sprint_id = uuid.UUID(str(raw))
    if "facilitator_user_id" in patch:
        raw = patch["facilitator_user_id"]
        session.facilitator_user_id = uuid.UUID(str(raw)) if raw else None
    if "status" in patch and patch["status"] is not None:
        status = str(patch["status"])
        if status not in SESSION_STATUSES:
            raise HTTPException(status_code=400, detail="status inválido")
        prev = session.status
        session.status = status
        if status == "active" and session.started_at is None:
            session.started_at = datetime.utcnow()
        if status == "closed" and prev != "closed":
            session.ended_at = datetime.utcnow()
    db.flush()
    return session


def delete_session(db: Session, session: ScrumCeremonySession) -> None:
    db.delete(session)
    db.flush()


def list_entries(db: Session, session_id: uuid.UUID) -> list[ScrumCeremonyEntry]:
    return list(
        db.scalars(
            select(ScrumCeremonyEntry)
            .where(ScrumCeremonyEntry.session_id == session_id)
            .order_by(ScrumCeremonyEntry.created_at.asc())
        )
    )


def create_entry(
    db: Session,
    *,
    session_id: uuid.UUID,
    author_user_id: uuid.UUID,
    entry_type: str,
    payload: dict[str, Any] | None,
) -> ScrumCeremonyEntry:
    row = ScrumCeremonyEntry(
        session_id=session_id,
        author_user_id=author_user_id,
        entry_type=entry_type,
        payload=payload or {},
    )
    db.add(row)
    db.flush()
    return row


def update_entry(
    db: Session,
    *,
    entry: ScrumCeremonyEntry,
    entry_type: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ScrumCeremonyEntry:
    if entry_type is not None:
        entry.entry_type = entry_type
    if payload is not None:
        entry.payload = payload
    db.flush()
    return entry


def delete_entry(db: Session, entry: ScrumCeremonyEntry) -> None:
    db.delete(entry)
    db.flush()
