"""Documento del proyecto con visibilidad por rol (§4.10)."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Document, Project
from app.schemas.documents import DocumentCreate, DocumentUpdate
from app.services.access import (
    assert_member_has_role,
    assert_project_active,
    document_visible_to_role,
)
from app.services.audit import record_audit_log


def get_document_for_viewer(
    db: Session,
    document: Document,
    *,
    viewer_rol: str | None,
) -> Document | None:
    if document_visible_to_role(document, viewer_rol=viewer_rol):  # type: ignore[arg-type]
        return document
    return None


def create_project_document(
    db: Session,
    project: Project,
    payload: DocumentCreate,
) -> Document:
    assert_project_active(project)
    assert_member_has_role(db, project.id, payload.created_by, "pm")

    document = Document(project_id=project.id, **payload.model_dump())
    db.add(document)
    db.flush()
    record_audit_log(
        db,
        project_id=project.id,
        user_id=payload.created_by,
        entidad_tipo="document",
        entidad_id=document.id,
        accion="created",
    )
    return document


def update_project_document(
    db: Session,
    document: Document,
    project: Project,
    payload: DocumentUpdate,
) -> None:
    assert_project_active(project)
    assert_member_has_role(db, project.id, payload.actor_user_id, "pm")

    changes = payload.model_dump(exclude_unset=True, exclude={"actor_user_id"})
    if not changes:
        return

    for field, nuevo in changes.items():
        anterior = getattr(document, field)
        if anterior == nuevo:
            continue
        setattr(document, field, nuevo)
        record_audit_log(
            db,
            project_id=project.id,
            user_id=payload.actor_user_id,
            entidad_tipo="document",
            entidad_id=document.id,
            accion="updated",
            campo=field,
            valor_anterior=str(anterior) if anterior is not None else None,
            valor_nuevo=str(nuevo) if nuevo is not None else None,
        )
