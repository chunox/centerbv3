from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.models.entities import DocumentExposure, User
from app.schemas.document_exposures import (
    DocumentExposureAmbito,
    DocumentExposureCreate,
    DocumentExposureRead,
    DocumentExposureUpdate,
)
from app.schemas.projects import MemberRol
from app.services.access import assert_member_of_project, list_exposures_for_viewer
from app.services.document_exposures import (
    create_document_exposure,
    delete_document_exposure,
    update_document_exposure,
)

router = APIRouter(tags=["document-exposures"])


@router.get(
    "/{project_id}/document-exposures",
    response_model=list[DocumentExposureRead],
)
def list_project_document_exposures(
    project_id: UUID,
    ambito: DocumentExposureAmbito | None = Query(default=None),
    milestone_id: UUID | None = Query(default=None),
    feature_id: UUID | None = Query(default=None),
    viewer_user_id: UUID | None = Query(default=None),
    viewer_rol: MemberRol | None = Query(default=None),
    db: Session = Depends(get_db),
):
    get_project_or_404(project_id, db)
    if viewer_user_id is not None:
        assert_member_of_project(db, project_id, viewer_user_id)
    exposures = list_exposures_for_viewer(
        db,
        project_id,
        viewer_rol=viewer_rol,
        milestone_id=milestone_id,
        feature_id=feature_id,
    )
    if ambito is not None:
        exposures = [e for e in exposures if e.ambito == ambito]
    return exposures


@router.post(
    "/{project_id}/document-exposures",
    response_model=DocumentExposureRead,
    status_code=201,
)
def create_project_document_exposure(
    project_id: UUID,
    payload: DocumentExposureCreate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    exposer = db.get(User, payload.expuesto_por)
    if not exposer:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    exposure = create_document_exposure(db, project, payload)
    db.commit()
    db.refresh(exposure)
    return exposure


@router.get(
    "/{project_id}/document-exposures/{exposure_id}",
    response_model=DocumentExposureRead,
)
def get_project_document_exposure(
    project_id: UUID, exposure_id: UUID, db: Session = Depends(get_db)
):
    get_project_or_404(project_id, db)
    exposure = db.get(DocumentExposure, exposure_id)
    if not exposure or exposure.project_id != project_id:
        raise HTTPException(status_code=404, detail="Exposición no encontrada")
    return exposure


@router.patch(
    "/{project_id}/document-exposures/{exposure_id}",
    response_model=DocumentExposureRead,
)
def patch_document_exposure(
    project_id: UUID,
    exposure_id: UUID,
    payload: DocumentExposureUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    exposure = db.get(DocumentExposure, exposure_id)
    if not exposure or exposure.project_id != project_id:
        raise HTTPException(status_code=404, detail="Exposición no encontrada")

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    update_document_exposure(db, exposure, project, payload)
    db.commit()
    db.refresh(exposure)
    return exposure


@router.delete(
    "/{project_id}/document-exposures/{exposure_id}",
    status_code=204,
)
def remove_document_exposure(
    project_id: UUID,
    exposure_id: UUID,
    actor_user_id: UUID,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    exposure = db.get(DocumentExposure, exposure_id)
    if not exposure or exposure.project_id != project_id:
        raise HTTPException(status_code=404, detail="Exposición no encontrada")

    actor = db.get(User, actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    delete_document_exposure(
        db, exposure, project, actor_user_id=actor_user_id
    )
    db.commit()
