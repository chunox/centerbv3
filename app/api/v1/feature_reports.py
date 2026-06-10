from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_feature_or_404, get_milestone_or_404, get_project_or_404
from app.database import get_db
from app.models.entities import Feature, FeatureReport, User
from app.schemas.feature_reports import (
    FeatureReportAction,
    FeatureReportCreate,
    FeatureReportInboxRead,
    FeatureReportRead,
)
from app.domain.capabilities import REPORT_CREATE
from app.services.access import assert_project_active
from app.services.workflow.authorize import assert_capability
from app.services.feature_reports import apply_report_action, notify_pms_report_received

router = APIRouter(tags=["feature-reports"])
inbox_router = APIRouter(tags=["feature-reports"])


def _get_report_in_project_or_404(
    project_id: UUID, report_id: UUID, db: Session
) -> tuple[FeatureReport, Feature]:
    report = db.get(FeatureReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    feature = db.get(Feature, report.feature_id)
    if not feature or feature.project_id != project_id:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return report, feature


@router.get(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/reports",
    response_model=list[FeatureReportRead],
)
def list_feature_reports(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    db: Session = Depends(get_db),
):
    get_feature_or_404(project_id, milestone_id, feature_id, db)
    stmt = (
        select(FeatureReport)
        .where(FeatureReport.feature_id == feature_id)
        .order_by(FeatureReport.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.post(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/reports",
    response_model=FeatureReportRead,
    status_code=201,
)
def create_feature_report(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    payload: FeatureReportCreate,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    assert_project_active(project)
    assert_capability(db, project.id, payload.reported_by, REPORT_CREATE)

    if feature.estado != "completado":
        raise HTTPException(
            status_code=409,
            detail="Solo se puede reportar sobre una feature en estado completado",
        )
    if project.tipo not in ("con_cliente", "freestyle"):
        raise HTTPException(
            status_code=400,
            detail="Los reportes solo aplican a proyectos con cliente",
        )

    reporter = db.get(User, payload.reported_by)
    if not reporter:
        raise HTTPException(status_code=404, detail="Usuario reportador no encontrado")

    report = FeatureReport(
        feature_id=feature_id,
        reported_by=payload.reported_by,
        tipo=payload.tipo,
        descripcion=payload.descripcion,
    )
    db.add(report)
    db.flush()
    notify_pms_report_received(db, project, report)
    db.commit()
    db.refresh(report)
    return report


@router.get(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/reports/{report_id}",
    response_model=FeatureReportRead,
)
def get_feature_report(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    report_id: UUID,
    db: Session = Depends(get_db),
):
    get_feature_or_404(project_id, milestone_id, feature_id, db)
    report = db.get(FeatureReport, report_id)
    if not report or report.feature_id != feature_id:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return report


@router.post(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/reports/{report_id}/actions",
    response_model=FeatureReportRead,
)
def perform_report_action(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    report_id: UUID,
    payload: FeatureReportAction,
    db: Session = Depends(get_db),
):
    original = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    milestone = get_milestone_or_404(project_id, milestone_id, db)

    report = db.get(FeatureReport, report_id)
    if not report or report.feature_id != feature_id:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    apply_report_action(
        db,
        report,
        original,
        project,
        milestone,
        action=payload.action,
        actor_user_id=payload.actor_user_id,
        duracion_estimada=payload.duracion_estimada,
        nombre_feature=payload.nombre_feature,
        form_data=payload.form_data,
    )
    db.commit()
    db.refresh(report)
    return report


@inbox_router.get(
    "/{project_id}/feature-reports",
    response_model=list[FeatureReportInboxRead],
)
def list_project_feature_reports(
    project_id: UUID,
    estado: str | None = Query(default=None),
    reported_by: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Bandeja PM / Cliente: reportes del proyecto con contexto de feature."""
    get_project_or_404(project_id, db)
    stmt = (
        select(FeatureReport, Feature)
        .join(Feature, Feature.id == FeatureReport.feature_id)
        .where(Feature.project_id == project_id)
        .order_by(FeatureReport.updated_at.desc())
    )
    if estado is not None:
        stmt = stmt.where(FeatureReport.estado == estado)
    if reported_by is not None:
        stmt = stmt.where(FeatureReport.reported_by == reported_by)

    rows = db.execute(stmt).all()
    return [
        FeatureReportInboxRead(
            id=report.id,
            feature_id=report.feature_id,
            reported_by=report.reported_by,
            tipo=report.tipo,  # type: ignore[arg-type]
            descripcion=report.descripcion,
            estado=report.estado,  # type: ignore[arg-type]
            generated_feature_id=report.generated_feature_id,
            created_at=report.created_at,
            updated_at=report.updated_at,
            project_id=feature.project_id,
            milestone_id=feature.milestone_id,
            feature_nombre=feature.nombre,
            feature_estado=feature.estado,
        )
        for report, feature in rows
    ]


@inbox_router.post(
    "/{project_id}/feature-reports/{report_id}/actions",
    response_model=FeatureReportRead,
)
def perform_project_report_action(
    project_id: UUID,
    report_id: UUID,
    payload: FeatureReportAction,
    db: Session = Depends(get_db),
):
    """Aprobar/rechazar desde bandeja PM sin ruta anidada milestone/feature."""
    report, original = _get_report_in_project_or_404(project_id, report_id, db)
    project = get_project_or_404(project_id, db)
    milestone = get_milestone_or_404(project_id, original.milestone_id, db)

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    apply_report_action(
        db,
        report,
        original,
        project,
        milestone,
        action=payload.action,
        actor_user_id=payload.actor_user_id,
        duracion_estimada=payload.duracion_estimada,
        nombre_feature=payload.nombre_feature,
        form_data=payload.form_data,
    )
    db.commit()
    db.refresh(report)
    return report
