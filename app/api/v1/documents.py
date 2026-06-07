from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.models.entities import Document, User
from app.schemas.documents import DocumentCreate, DocumentRead, DocumentUpdate
from app.schemas.projects import MemberRol
from app.services.documents import (
    create_project_document,
    get_document_for_viewer,
    update_project_document,
)

router = APIRouter(tags=["documents"])


def _get_project_document_or_404(
    project_id: UUID, document_id: UUID, db: Session
) -> Document:
    get_project_or_404(project_id, db)
    document = db.get(Document, document_id)
    if not document or document.project_id != project_id:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return document


@router.get("/{project_id}/document", response_model=DocumentRead | None)
def get_project_document(
    project_id: UUID,
    viewer_rol: MemberRol | None = Query(default=None),
    db: Session = Depends(get_db),
):
    get_project_or_404(project_id, db)
    document = db.scalar(select(Document).where(Document.project_id == project_id))
    if document is None:
        return None
    visible = get_document_for_viewer(db, document, viewer_rol=viewer_rol)
    if visible is None:
        raise HTTPException(
            status_code=403,
            detail="No tienes permiso para ver este documento",
        )
    return visible


@router.post("/{project_id}/document", response_model=DocumentRead, status_code=201)
def create_project_document_endpoint(
    project_id: UUID, payload: DocumentCreate, db: Session = Depends(get_db)
):
    project = get_project_or_404(project_id, db)
    creator = db.get(User, payload.created_by)
    if not creator:
        raise HTTPException(status_code=404, detail="Usuario creador no encontrado")

    existing = db.scalar(select(Document).where(Document.project_id == project_id))
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Este proyecto ya tiene un documento (solo se permite uno)",
        )

    try:
        document = create_project_document(db, project, payload)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Este proyecto ya tiene un documento (solo se permite uno)",
        )
    db.refresh(document)
    return document


@router.patch("/{project_id}/document", response_model=DocumentRead)
def update_project_document_endpoint(
    project_id: UUID, payload: DocumentUpdate, db: Session = Depends(get_db)
):
    project = get_project_or_404(project_id, db)
    document = db.scalar(select(Document).where(Document.project_id == project_id))
    if not document:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    update_project_document(db, document, project, payload)
    db.commit()
    db.refresh(document)
    return document


@router.get("/{project_id}/document/{document_id}", response_model=DocumentRead)
def get_document(
    project_id: UUID,
    document_id: UUID,
    viewer_rol: MemberRol | None = Query(default=None),
    db: Session = Depends(get_db),
):
    document = _get_project_document_or_404(project_id, document_id, db)
    visible = get_document_for_viewer(db, document, viewer_rol=viewer_rol)
    if visible is None:
        raise HTTPException(
            status_code=403,
            detail="No tienes permiso para ver este documento",
        )
    return visible
