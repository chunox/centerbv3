"""Aprobación y rechazo de reportes post-entrega (§4.7)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.domain.capabilities import REPORT_APPROVE, REPORT_REJECT, WORKBENCH_INBOX_PM
from app.services.feature_queries import assert_project_active
from app.services.workflow.authorize import assert_capability
from app.services.notifications import create_notification
from app.services.records.repository import _data
from app.services.workflow.capabilities import users_with_capability

ReportAction = Literal["aprobar", "rechazar"]


def _report_generated_feature_id(report: ProjectRecord) -> uuid.UUID | None:
    raw = _data(report).get("generated_feature_id")
    return uuid.UUID(raw) if raw else None


def _report_tipo(report: ProjectRecord) -> str:
    return str(_data(report).get("tipo", "bug"))


def _default_hotfix_nombre(original: ProjectRecord, report: ProjectRecord) -> str:
    label = "Hotfix" if _report_tipo(report) == "bug" else "Mejora"
    return f"{label}: {original.titulo}"


def _extend_milestone_for_mejora(
    milestone: ProjectRecord, duracion_estimada: int
) -> None:
    if milestone.fecha_fin is not None:
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


def apply_report_action(
    db: Session,
    report: ProjectRecord,
    original: ProjectRecord,
    project: Project,
    milestone: ProjectRecord,
    *,
    action: ReportAction,
    actor_user_id: uuid.UUID,
    duracion_estimada: int | None = None,
    nombre_feature: str | None = None,
    form_data: dict[str, Any] | None = None,
) -> ProjectRecord | None:
    from app.services.workflow.engine import apply_entity_transition

    assert_project_active(project)
    cap = REPORT_APPROVE if action == "aprobar" else REPORT_REJECT
    assert_capability(db, project.id, actor_user_id, cap)

    from app.services.project_profile import supports_reports

    if not supports_reports(db, project):
        raise HTTPException(
            status_code=400,
            detail="Los reportes solo aplican a proyectos con stakeholder externo",
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

    if action == "aprobar" and _report_tipo(report) == "mejora":
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
    if action == "aprobar":
        gen_id = _report_generated_feature_id(report)
        if gen_id:
            return db.get(ProjectRecord, gen_id)
    return None


def notify_pms_report_received(
    db: Session, project: Project, report: ProjectRecord
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
