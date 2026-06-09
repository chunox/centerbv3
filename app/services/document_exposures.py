"""Exposición de documentación al cliente (§4.10)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import DocumentExposure, HubEntry, Project
from app.schemas.document_exposures import (
    DocumentExposureCreate,
    DocumentExposureUpdate,
)
from app.services.access import assert_member_has_role, assert_project_active
from app.services.audit import record_audit_log

DocumentExposureAmbito = Literal["proyecto", "milestone", "feature"]


def list_document_exposures(
    db: Session,
    project_id: uuid.UUID,
    *,
    ambito: DocumentExposureAmbito | None = None,
    milestone_id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
) -> list[DocumentExposure]:
    stmt = select(DocumentExposure).where(DocumentExposure.project_id == project_id)
    if ambito is not None:
        stmt = stmt.where(DocumentExposure.ambito == ambito)
    if milestone_id is not None:
        stmt = stmt.where(DocumentExposure.milestone_id == milestone_id)
    if feature_id is not None:
        stmt = stmt.where(DocumentExposure.feature_id == feature_id)
    return list(db.scalars(stmt.order_by(DocumentExposure.created_at.desc())))


def create_document_exposure(
    db: Session,
    project: Project,
    payload: DocumentExposureCreate,
) -> DocumentExposure:
    assert_project_active(project)
    assert_member_has_role(db, project.id, payload.expuesto_por, "pm")

    if payload.hub_entry_id is not None:
        entry = db.get(HubEntry, payload.hub_entry_id)
        if not entry or entry.project_id != project.id:
            raise HTTPException(status_code=404, detail="Publicación no encontrada en el proyecto")

    exposure = DocumentExposure(project_id=project.id, **payload.model_dump())
    db.add(exposure)
    db.flush()
    record_audit_log(
        db,
        project_id=project.id,
        user_id=payload.expuesto_por,
        entidad_tipo="document",
        entidad_id=exposure.id,
        accion="created",
    )
    return exposure


def update_document_exposure(
    db: Session,
    exposure: DocumentExposure,
    project: Project,
    payload: DocumentExposureUpdate,
) -> None:
    assert_project_active(project)
    assert_member_has_role(db, project.id, payload.actor_user_id, "pm")

    if payload.titulo_visible is not None:
        anterior = exposure.titulo_visible
        exposure.titulo_visible = payload.titulo_visible
        if anterior != payload.titulo_visible:
            record_audit_log(
                db,
                project_id=project.id,
                user_id=payload.actor_user_id,
                entidad_tipo="document",
                entidad_id=exposure.id,
                accion="updated",
                campo="titulo_visible",
                valor_anterior=anterior,
                valor_nuevo=payload.titulo_visible,
            )


def delete_document_exposure(
    db: Session,
    exposure: DocumentExposure,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_member_has_role(db, project.id, actor_user_id, "pm")
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="document",
        entidad_id=exposure.id,
        accion="deleted",
    )
    db.delete(exposure)
