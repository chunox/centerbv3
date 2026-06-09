"""Entradas del centro del proyecto — updates y notas."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import HubEntry, Project, User
from app.schemas.hub_entries import HubEntryCreate, HubEntryUpdate
from app.schemas.projects import MemberRol
from app.services.access import (
    assert_member_has_role,
    assert_member_of_project,
    assert_pm_or_dev_member,
    assert_project_active,
    hub_entry_visible_to_role,
)
from app.services.audit import record_audit_log

HubEntryTipoFilter = Literal["update", "note"]


def list_hub_entries(
    db: Session,
    project_id: uuid.UUID,
    *,
    viewer_rol: MemberRol | None = None,
    tipo: HubEntryTipoFilter | None = None,
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
    if viewer_rol is None:
        return entries
    return [e for e in entries if hub_entry_visible_to_role(e, viewer_rol=viewer_rol)]


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
    assert_pm_or_dev_member(db, project.id, payload.author_id)

    author = db.get(User, payload.author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Autor no encontrado")

    entry = HubEntry(
        project_id=project.id,
        author_id=payload.author_id,
        tipo=payload.tipo,
        titulo=payload.titulo.strip() if payload.titulo else None,
        contenido=payload.contenido.strip(),
        visibilidad=payload.visibilidad,
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
    if entry.author_id == actor_user_id:
        assert_pm_or_dev_member(db, entry.project_id, actor_user_id)
        return
    assert_member_has_role(db, entry.project_id, actor_user_id, "pm")


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
        data = {
            "id": entry.id,
            "project_id": entry.project_id,
            "author_id": entry.author_id,
            "author_nombre": authors.get(entry.author_id),
            "tipo": entry.tipo,
            "titulo": entry.titulo,
            "contenido": entry.contenido,
            "visibilidad": entry.visibilidad,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        result.append(data)
    return result
