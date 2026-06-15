"""Entradas del hub del proyecto — updates, notas, shortcuts, páginas y canvas."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import HubEntry, Project, ProjectMember, ProjectRecord, ProjectRole, User
from app.schemas.hub_entries import HubEntryCreate, HubEntryUpdate
from app.domain.capabilities import HUB_PUBLISH
from app.services.access import (
    assert_member_of_project,
    assert_project_active,
    hub_entry_visible_for_user,
)
from app.services.workflow.authorize import assert_capability
from app.services.audit import record_audit_log

HubEntryTipoFilter = str | None


def _viewer_role_slug(
    db: Session,
    project_id: uuid.UUID,
    viewer_user_id: uuid.UUID,
) -> str | None:
    row = db.scalar(
        select(ProjectRole.slug)
        .join(ProjectMember, ProjectMember.role_id == ProjectRole.id)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == viewer_user_id,
        )
        .limit(1)
    )
    return row


def list_hub_entries(
    db: Session,
    project_id: uuid.UUID,
    *,
    viewer_user_id: uuid.UUID | None = None,
    tipo: HubEntryTipoFilter = None,
    limit: int = 50,
    offset: int = 0,
) -> list[HubEntry]:
    stmt = (
        select(HubEntry)
        .where(HubEntry.project_id == project_id)
        .order_by(HubEntry.created_at.desc())
        .limit(min(limit, 100))
        .offset(offset)
    )
    if tipo is not None:
        stmt = stmt.where(HubEntry.tipo == tipo)
    entries = list(db.scalars(stmt))
    if viewer_user_id is None:
        return entries
    role_slug = _viewer_role_slug(db, project_id, viewer_user_id)
    return [
        e
        for e in entries
        if hub_entry_visible_for_user(
            db, e, viewer_user_id=viewer_user_id, viewer_role_slug=role_slug
        )
    ]


def get_hub_entry_or_404(
    db: Session,
    project_id: uuid.UUID,
    entry_id: uuid.UUID,
) -> HubEntry:
    entry = db.get(HubEntry, entry_id)
    if not entry or entry.project_id != project_id:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    return entry


def create_hub_entry(
    db: Session,
    project: Project,
    payload: HubEntryCreate,
) -> HubEntry:
    assert_project_active(project)
    assert_capability(db, project.id, payload.author_id, HUB_PUBLISH)

    author = db.get(User, payload.author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Autor no encontrado")

    if payload.record_id is not None:
        record = db.get(ProjectRecord, payload.record_id)
        if not record or record.project_id != project.id:
            raise HTTPException(status_code=404, detail="Record no encontrado")

    entry = HubEntry(
        project_id=project.id,
        author_id=payload.author_id,
        tipo=payload.tipo,
        titulo=payload.titulo.strip() if payload.titulo else None,
        contenido=payload.contenido.strip() if payload.contenido else "",
        visible_roles=payload.visible_roles or [],
        record_id=payload.record_id,
    )
    db.add(entry)
    db.flush()
    record_audit_log(
        db,
        project_id=project.id,
        user_id=payload.author_id,
        entidad_tipo="hub_entry",
        entidad_id=entry.id,
        accion="created",
    )
    return entry


def _assert_hub_entry_edit_allowed(
    db: Session,
    entry: HubEntry,
    actor_user_id: uuid.UUID,
) -> None:
    assert_capability(db, entry.project_id, actor_user_id, HUB_PUBLISH)


def update_hub_entry(
    db: Session,
    entry: HubEntry,
    project: Project,
    payload: HubEntryUpdate,
) -> None:
    assert_project_active(project)
    _assert_hub_entry_edit_allowed(db, entry, payload.actor_user_id)

    changes = payload.model_dump(exclude_unset=True, exclude={"actor_user_id"})
    if not changes:
        return

    if entry.tipo == "note" and changes.get("titulo") is not None:
        titulo = changes["titulo"]
        if not titulo or not str(titulo).strip():
            raise HTTPException(status_code=422, detail="Las notas requieren título")

    for field, nuevo in changes.items():
        anterior = getattr(entry, field)
        if field == "titulo" and isinstance(nuevo, str):
            nuevo = nuevo.strip() or None
        if field == "contenido" and isinstance(nuevo, str):
            nuevo = nuevo.strip()
        if anterior == nuevo:
            continue
        setattr(entry, field, nuevo)
        record_audit_log(
            db,
            project_id=project.id,
            user_id=payload.actor_user_id,
            entidad_tipo="hub_entry",
            entidad_id=entry.id,
            accion="updated",
            campo=field,
            valor_anterior=str(anterior) if anterior is not None else None,
            valor_nuevo=str(nuevo) if nuevo is not None else None,
        )


def delete_hub_entry(
    db: Session,
    entry: HubEntry,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    _assert_hub_entry_edit_allowed(db, entry, actor_user_id)
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="hub_entry",
        entidad_id=entry.id,
        accion="deleted",
    )
    db.delete(entry)


def _enrich_shortcut(db: Session, entry: HubEntry) -> dict[str, Any] | None:
    if entry.record_id is None:
        return None
    record = db.get(ProjectRecord, entry.record_id)
    if record is None:
        return None
    return {
        "id": str(record.id),
        "record_type": record.record_type,
        "estado": record.estado,
        "titulo": record.data.get("titulo") if isinstance(record.data, dict) else None,
    }


def enrich_hub_entries_with_authors(
    db: Session,
    entries: list[HubEntry],
) -> list[dict]:
    if not entries:
        return []
    author_ids = {e.author_id for e in entries}
    authors = {
        u.id: u.nombre
        for u in db.scalars(select(User).where(User.id.in_(author_ids)))
    }
    result: list[dict] = []
    for entry in entries:
        data: dict[str, Any] = {
            "id": entry.id,
            "project_id": entry.project_id,
            "author_id": entry.author_id,
            "author_nombre": authors.get(entry.author_id),
            "tipo": entry.tipo,
            "titulo": entry.titulo,
            "contenido": entry.contenido,
            "visible_roles": entry.visible_roles or [],
            "record_id": entry.record_id,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        if entry.tipo == "shortcut":
            data["shortcut_record"] = _enrich_shortcut(db, entry)
        result.append(data)
    return result
