"""Control de acceso sin JWT — actor_user_id / viewer_rol en query/body (demo)."""

from __future__ import annotations

import re
import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AuditLog,
    Comment,
    Document,
    DocumentExposure,
    Feature,
    FeatureQuery,
    FeatureReport,
    Milestone,
    Project,
    ProjectMember,
    Task,
)

MemberRol = Literal["pm", "dev", "qa", "cliente"]

MENTION_UUID_RE = re.compile(
    r"@([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)

ROLE_AUDIT_ENTIDADES: dict[MemberRol, frozenset[str]] = {
    "pm": frozenset(
        {
            "project",
            "milestone",
            "feature",
            "tarea",
            "feature_query",
            "feature_report",
            "document",
            "comment",
        }
    ),
    "dev": frozenset({"feature", "tarea", "comment"}),
    "qa": frozenset({"feature", "tarea", "comment"}),
    "cliente": frozenset({"feature", "feature_query", "feature_report", "comment"}),
}


def assert_project_active(project: Project) -> None:
    if project.estado != "activo":
        raise HTTPException(
            status_code=409,
            detail="El proyecto no está activo; no se pueden realizar modificaciones",
        )


def assert_member_has_role(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    rol: MemberRol,
) -> None:
    stmt = select(
        exists().where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.rol == rol,
        )
    )
    if not db.scalar(stmt):
        raise HTTPException(
            status_code=403,
            detail=f"El usuario no tiene rol '{rol}' en este proyecto",
        )


def assert_member_of_project(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    stmt = select(
        exists().where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    if not db.scalar(stmt):
        raise HTTPException(
            status_code=403,
            detail="El usuario no es miembro de este proyecto",
        )


def assert_not_pm_for_task_ops(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """PM no crea ni mueve tareas (§4.6)."""
    is_pm = db.scalar(
        select(
            exists().where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.rol == "pm",
            )
        )
    )
    if is_pm:
        raise HTTPException(
            status_code=403,
            detail="El PM no puede crear ni editar tareas",
        )


def get_project_id_for_comment_entity(
    db: Session,
    entidad_tipo: str,
    entidad_id: uuid.UUID,
) -> uuid.UUID:
    if entidad_tipo == "feature":
        row = db.get(Feature, entidad_id)
        if not row:
            raise HTTPException(status_code=404, detail="Feature no encontrada")
        return row.project_id
    if entidad_tipo == "tarea":
        row = db.get(Task, entidad_id)
        if not row:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        return row.project_id
    if entidad_tipo == "feature_query":
        row = db.get(FeatureQuery, entidad_id)
        if not row:
            raise HTTPException(status_code=404, detail="Consulta no encontrada")
        feature = db.get(Feature, row.feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail="Feature no encontrada")
        return feature.project_id
    if entidad_tipo == "feature_report":
        row = db.get(FeatureReport, entidad_id)
        if not row:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        feature = db.get(Feature, row.feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail="Feature no encontrada")
        return feature.project_id
    raise HTTPException(status_code=400, detail="Tipo de entidad no soportado")


def get_project_id_for_attachment_entity(
    db: Session,
    entidad_tipo: str,
    entidad_id: uuid.UUID,
) -> uuid.UUID:
    if entidad_tipo == "document":
        row = db.get(Document, entidad_id)
        if not row:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        return row.project_id
    return get_project_id_for_comment_entity(db, entidad_tipo, entidad_id)


def parse_mention_user_ids(contenido: str) -> list[uuid.UUID]:
    seen: set[uuid.UUID] = set()
    result: list[uuid.UUID] = []
    for match in MENTION_UUID_RE.finditer(contenido):
        uid = uuid.UUID(match.group(1))
        if uid not in seen:
            seen.add(uid)
            result.append(uid)
    return result


def document_visible_to_role(
    document: Document,
    *,
    viewer_rol: MemberRol | None,
) -> bool:
    if viewer_rol is None:
        return True
    if viewer_rol == "cliente" and document.visibilidad == "interno":
        return False
    return True


def filter_audit_logs_for_viewer(
    db: Session,
    logs: list[AuditLog],
    *,
    viewer_user_id: uuid.UUID | None,
    viewer_rol: MemberRol | None,
) -> list[AuditLog]:
    if viewer_rol is None or viewer_rol == "pm":
        return logs

    allowed_types = ROLE_AUDIT_ENTIDADES.get(viewer_rol, frozenset())
    filtered: list[AuditLog] = []

    assigned_task_ids: set[uuid.UUID] | None = None
    own_report_ids: set[uuid.UUID] | None = None
    if viewer_user_id and viewer_rol == "dev":
        assigned_task_ids = set(
            db.scalars(
                select(Task.id).where(Task.asignado_a == viewer_user_id)
            )
        )
    if viewer_user_id and viewer_rol == "cliente":
        own_report_ids = set(
            db.scalars(
                select(FeatureReport.id).where(
                    FeatureReport.reported_by == viewer_user_id
                )
            )
        )

    for log in logs:
        if log.entidad_tipo not in allowed_types:
            continue
        if viewer_rol == "dev" and viewer_user_id:
            if log.user_id == viewer_user_id:
                filtered.append(log)
                continue
            if log.entidad_tipo == "tarea" and assigned_task_ids:
                if log.entidad_id in assigned_task_ids:
                    filtered.append(log)
                continue
            if log.entidad_tipo in ("feature", "comment"):
                filtered.append(log)
            continue
        if viewer_rol == "qa":
            if log.entidad_tipo == "feature":
                feature = db.get(Feature, log.entidad_id)
                if feature and feature.estado in (
                    "uat",
                    "esperando_liberacion_pm",
                    "esperando_validacion_cliente",
                    "completado",
                ):
                    filtered.append(log)
                continue
            filtered.append(log)
            continue
        if viewer_rol == "cliente" and viewer_user_id:
            if log.user_id == viewer_user_id:
                filtered.append(log)
                continue
            if log.entidad_tipo == "feature_report" and own_report_ids:
                if log.entidad_id in own_report_ids:
                    filtered.append(log)
                continue
            if log.entidad_tipo in ("feature", "feature_query", "comment"):
                filtered.append(log)
            continue
        filtered.append(log)

    return filtered


def assert_attachment_author_or_pm(
    db: Session,
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    *,
    uploaded_by: uuid.UUID,
) -> None:
    """PATCH/DELETE adjunto: solo autor o PM (§4.11)."""
    if actor_user_id == uploaded_by:
        return
    assert_member_has_role(db, project_id, actor_user_id, "pm")


def list_exposures_for_viewer(
    db: Session,
    project_id: uuid.UUID,
    *,
    viewer_rol: MemberRol | None,
    milestone_id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
) -> list[DocumentExposure]:
    stmt = select(DocumentExposure).where(DocumentExposure.project_id == project_id)
    if milestone_id is not None:
        stmt = stmt.where(DocumentExposure.milestone_id == milestone_id)
    if feature_id is not None:
        stmt = stmt.where(DocumentExposure.feature_id == feature_id)
    exposures = list(db.scalars(stmt.order_by(DocumentExposure.created_at.desc())))
    if viewer_rol != "cliente":
        return exposures
    # Cliente: solo filas de exposición explícita (sin documentos internos no expuestos)
    filtered: list[DocumentExposure] = []
    for exp in exposures:
        if exp.document_id is not None:
            doc = db.get(Document, exp.document_id)
            if doc and doc.visibilidad == "interno":
                continue
        filtered.append(exp)
    return filtered
