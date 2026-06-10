"""Aprobación y rechazo de reportes post-entrega (§4.7)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Feature, FeatureReport, Milestone, Project
from app.services.audit import record_audit_log
from app.domain.capabilities import REPORT_APPROVE, REPORT_REJECT, WORKBENCH_INBOX_PM
from app.services.feature_queries import assert_project_active
from app.services.workflow.authorize import assert_capability
from app.services.features import ensure_default_task
from app.services.milestones import sync_milestone_state
from app.services.notifications import create_notification
from app.services.workflow.capabilities import users_with_capability

ReportAction = Literal["aprobar", "rechazar"]


def _default_hotfix_nombre(original: Feature, report: FeatureReport) -> str:
    label = "Hotfix" if report.tipo == "bug" else "Mejora"
    return f"{label}: {original.nombre}"


def _extend_milestone_for_mejora(
    milestone: Milestone, duracion_estimada: int
) -> None:
    milestone.fecha_fin = milestone.fecha_fin + timedelta(days=duracion_estimada)


def _merge_form_data(
    form_data: dict[str, Any] | None,
    *,
    duracion_estimada: int | None = None,
    nombre_feature: str | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(form_data or {})
    if nombre_feature is not None and "nombre_feature" not in merged:
        merged["nombre_feature"] = nombre_feature
    if duracion_estimada is not None and "duracion_estimada" not in merged:
        merged["duracion_estimada"] = duracion_estimada
    return merged


def _parse_duracion(form_data: dict[str, Any] | None) -> int | None:
    if not form_data:
        return None
    raw = form_data.get("duracion_estimada")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def generate_feature_from_report(
    db: Session,
    report: FeatureReport,
    original: Feature,
    project: Project,
    milestone: Milestone,
    *,
    actor_user_id: uuid.UUID,
    form_data: dict[str, Any] | None,
) -> Feature:
    if report.tipo == "mejora":
        duracion = _parse_duracion(form_data)
        if duracion is None or duracion < 1:
            raise HTTPException(
                status_code=422,
                detail="duracion_estimada es obligatoria al aprobar un reporte mejora",
            )
    else:
        duracion = None

    nombre_raw = (form_data or {}).get("nombre_feature")
    nombre_feature = (
        str(nombre_raw).strip()
        if isinstance(nombre_raw, str) and nombre_raw.strip()
        else None
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
        duracion_estimada=duracion if report.tipo == "mejora" else None,
        estado="pendiente",
        origen_report_id=report.id,
        origen_feature_id=original.id,
        created_by=actor_user_id,
    )
    db.add(generated)
    db.flush()

    ensure_default_task(db, generated, created_by=actor_user_id)

    if report.tipo == "mejora" and duracion is not None:
        _extend_milestone_for_mejora(milestone, duracion)

    report.generated_feature_id = generated.id

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
    return generated


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
    form_data: dict[str, Any] | None = None,
) -> Feature | None:
    from app.services.workflow.engine import apply_entity_transition

    assert_project_active(project)
    cap = REPORT_APPROVE if action == "aprobar" else REPORT_REJECT
    assert_capability(db, project.id, actor_user_id, cap)

    if project.tipo not in ("con_cliente", "freestyle"):
        raise HTTPException(
            status_code=400,
            detail="Los reportes solo aplican a proyectos con cliente",
        )
    if report.estado != "pendiente":
        raise HTTPException(
            status_code=409,
            detail=f"El reporte ya está en estado {report.estado}",
        )

    merged_form = _merge_form_data(
        form_data,
        duracion_estimada=duracion_estimada,
        nombre_feature=nombre_feature,
    )

    if action == "aprobar" and report.tipo == "mejora":
        duracion = _parse_duracion(merged_form)
        if duracion is None or duracion < 1:
            raise HTTPException(
                status_code=422,
                detail="duracion_estimada es obligatoria al aprobar un reporte mejora",
            )

    apply_entity_transition(
        db,
        project,
        report,
        entity_type="report",
        action_id=action,
        actor_user_id=actor_user_id,
        form_data=merged_form,
        side_effect_context={
            "milestone_id": milestone.id,
            "form_data": merged_form,
        },
    )
    if action == "aprobar" and report.generated_feature_id:
        return db.get(Feature, report.generated_feature_id)
    return None


def notify_pms_report_received(
    db: Session, project: Project, report: FeatureReport
) -> None:
    for pm_id in users_with_capability(db, project.id, WORKBENCH_INBOX_PM):
        create_notification(
            db,
            user_id=pm_id,
            project_id=project.id,
            tipo="reporte_recibido",
            entidad_tipo="feature_report",
            entidad_id=report.id,
        )
