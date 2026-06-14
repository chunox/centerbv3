"""Validación al crear features según tipo de proyecto (§4.5)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.schemas.features import FeatureCreate
from app.services.milestones import sync_milestone_state
from app.services.records.repository import _data, get_record, update_record_fields


def validate_and_prepare_feature_create(
    db: Session,
    project: Project,
    milestone: ProjectRecord,
    payload: FeatureCreate,
) -> None:
    if payload.tipo in ("bug", "mejora"):
        from app.services.project_profile import supports_external_stakeholder

        if supports_external_stakeholder(db, project):
            raise HTTPException(
                status_code=403,
                detail="En proyectos con cliente, bug/mejora solo se crean al aprobar un reporte",
            )
        if payload.origen_feature_id is None:
            raise HTTPException(
                status_code=422,
                detail="bug/mejora en interno requieren origen_feature_id",
            )
        origen = get_record(db, payload.origen_feature_id)
        if (
            not origen
            or origen.project_id != project.id
            or origen.record_type != "feature"
        ):
            raise HTTPException(status_code=404, detail="Feature origen no encontrada")
        if origen.estado != "completado":
            raise HTTPException(
                status_code=409,
                detail="La feature origen debe estar en completado",
            )
        if payload.tipo == "mejora" and payload.duracion_estimada is None:
            raise HTTPException(
                status_code=422,
                detail="duracion_estimada es obligatoria para tipo mejora",
            )
    elif payload.tipo == "desarrollo" and payload.origen_feature_id is not None:
        raise HTTPException(
            status_code=422,
            detail="origen_feature_id solo aplica a bug/mejora",
        )


def after_feature_created(
    db: Session,
    project: Project,
    milestone: ProjectRecord,
    feature: ProjectRecord,
    payload: FeatureCreate,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    from app.services.project_profile import supports_external_stakeholder

    if (
        not supports_external_stakeholder(db, project)
        and _data(feature).get("tipo") == "mejora"
        and payload.duracion_estimada
        and milestone.fecha_fin is not None
    ):
        update_record_fields(
            db,
            milestone,
            fecha_fin=milestone.fecha_fin + timedelta(days=payload.duracion_estimada),
        )
        sync_milestone_state(
            db, milestone, project, actor_user_id=actor_user_id
        )
