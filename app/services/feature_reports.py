"""Aprobación y rechazo de reportes post-entrega (§4.7)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Feature, FeatureReport, Milestone, Project
from app.services.audit import record_audit_log
from app.services.feature_queries import assert_member_has_role, assert_project_active
from app.services.features import ensure_default_task
from app.services.milestones import sync_milestone_state
from app.services.notifications import create_notification

ReportAction = Literal["aprobar", "rechazar"]


def _default_hotfix_nombre(original: Feature, report: FeatureReport) -> str:
    label = "Hotfix" if report.tipo == "bug" else "Mejora"
    return f"{label}: {original.nombre}"


def _extend_milestone_for_mejora(
    milestone: Milestone, duracion_estimada: int
) -> None:
    milestone.fecha_fin = milestone.fecha_fin + timedelta(days=duracion_estimada)


def apply_report_action(
    db: Session,
    report: FeatureReport,
    original: Feature,
    project: Project,
    milestone: Milestone,
    *,
    action: ReportAction,
    actor_user_id: uuid.UUID,
    duracion_estimada: int | None = None,
    nombre_feature: str | None = None,
) -> Feature | None:
    assert_project_active(project)
    assert_member_has_role(db, project.id, actor_user_id, "pm")

    if project.tipo != "con_cliente":
        raise HTTPException(
            status_code=400,
            detail="Los reportes solo aplican a proyectos con_cliente",
        )
    if report.estado != "pendiente":
        raise HTTPException(
            status_code=409,
            detail=f"El reporte ya está en estado {report.estado}",
        )
    if original.estado != "completado":
        raise HTTPException(
            status_code=409,
            detail="La feature original debe estar en completado",
        )

    if action == "rechazar":
        report.estado = "rechazado"
        create_notification(
            db,
            user_id=report.reported_by,
            project_id=project.id,
            tipo="reporte_resuelto",
            entidad_tipo="feature_report",
            entidad_id=report.id,
        )
        record_audit_log(
            db,
            project_id=project.id,
            user_id=actor_user_id,
            entidad_tipo="feature_report",
            entidad_id=report.id,
            accion="estado_changed",
            campo="estado",
            valor_anterior="pendiente",
            valor_nuevo="rechazado",
        )
        return None

    if report.tipo == "mejora" and (duracion_estimada is None or duracion_estimada < 1):
        raise HTTPException(
            status_code=422,
            detail="duracion_estimada es obligatoria al aprobar un reporte mejora",
        )

    hoy = date.today()
    generated = Feature(
        milestone_id=milestone.id,
        project_id=project.id,
        nombre=nombre_feature or _default_hotfix_nombre(original, report),
        descripcion=report.descripcion,
        tipo=report.tipo,
        prioridad="media",
        fecha_inicio=hoy,
        fecha_fin=milestone.fecha_fin,
        duracion_estimada=duracion_estimada if report.tipo == "mejora" else None,
        estado="pendiente",
        origen_report_id=report.id,
        origen_feature_id=original.id,
        created_by=actor_user_id,
    )
    db.add(generated)
    db.flush()

    ensure_default_task(db, generated, created_by=actor_user_id)

    if report.tipo == "mejora":
        _extend_milestone_for_mejora(milestone, duracion_estimada)  # type: ignore[arg-type]

    report.estado = "aprobado"
    report.generated_feature_id = generated.id

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="feature_report",
        entidad_id=report.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior="pendiente",
        valor_nuevo="aprobado",
    )
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="feature",
        entidad_id=generated.id,
        accion="feature_generada",
        campo="origen_report_id",
        valor_nuevo=str(report.id),
    )

    create_notification(
        db,
        user_id=report.reported_by,
        project_id=project.id,
        tipo="reporte_resuelto",
        entidad_tipo="feature_report",
        entidad_id=report.id,
    )

    sync_milestone_state(
        db, milestone, project, actor_user_id=actor_user_id
    )
    return generated


def notify_pms_report_received(
    db: Session, project: Project, report: FeatureReport
) -> None:
    from sqlalchemy import select

    from app.models.entities import ProjectMember

    for pm_id in db.scalars(
        select(ProjectMember.user_id).where(
            ProjectMember.project_id == project.id,
            ProjectMember.rol == "pm",
        )
    ):
        create_notification(
            db,
            user_id=pm_id,
            project_id=project.id,
            tipo="reporte_recibido",
            entidad_tipo="feature_report",
            entidad_id=report.id,
        )
