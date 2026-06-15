"""Control de acceso — actor_user_id en mutaciones; visibilidad por capacidades."""

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
    HubEntry,
    Project,
    ProjectMember,
    ProjectRecord,
    ProjectRole,
)

MemberRol = Literal["pm", "dev", "qa", "cliente"]

MENTION_UUID_RE = re.compile(
    r"@([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


def assert_project_active(project: Project) -> None:
    if project.estado != "activo":
        raise HTTPException(
            status_code=409,
            detail="El proyecto no está activo; no se pueden realizar modificaciones",
        )


def assert_pm_or_org_admin_of_project(
    db: Session,
    project: Project,
    user_id: uuid.UUID,
) -> None:
    """Capacidad de configuración del proyecto u owner/admin de la org."""
    from app.domain.capabilities import PROJECT_SETTINGS_EDIT
    from app.services.organizations import ORG_ADMIN_ROLES, get_org_member
    from app.services.workflow.authorize import assert_capability

    org_member = get_org_member(db, project.organization_id, user_id)
    if org_member and org_member.rol in ORG_ADMIN_ROLES:
        return
    assert_capability(db, project.id, user_id, PROJECT_SETTINGS_EDIT)


def _member_role_exists(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role_slugs: tuple[str, ...],
) -> bool:
    stmt = select(
        exists(
            select(ProjectMember.id)
            .join(ProjectRole, ProjectRole.id == ProjectMember.role_id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectRole.slug.in_(role_slugs),
            )
        )
    )
    return bool(db.scalar(stmt))


def assert_member_has_role(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    rol: MemberRol,
) -> None:
    if not _member_role_exists(db, project_id, user_id, (rol,)):
        raise HTTPException(
            status_code=403,
            detail=f"El usuario no tiene rol '{rol}' en este proyecto",
        )


def assert_pm_or_dev_member(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    is_allowed = _member_role_exists(
        db, project_id, user_id, ("pm", "dev", "tech_lead", "pm_tecnico")
    )
    if not is_allowed:
        raise HTTPException(
            status_code=403,
            detail="Solo PM, Dev, Tech Líder o PM Técnico pueden realizar esta acción",
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


def _project_id_for_record(
    db: Session, record_id: uuid.UUID, *, record_type: str, label: str
) -> uuid.UUID:
    row = db.get(ProjectRecord, record_id)
    if not row or row.record_type != record_type:
        raise HTTPException(status_code=404, detail=label)
    return row.project_id


def get_project_id_for_comment_entity(
    db: Session,
    entidad_tipo: str,
    entidad_id: uuid.UUID,
) -> uuid.UUID:
    if entidad_tipo == "feature":
        return _project_id_for_record(
            db, entidad_id, record_type="feature", label="Feature no encontrada"
        )
    if entidad_tipo == "tarea":
        return _project_id_for_record(
            db, entidad_id, record_type="task", label="Tarea no encontrada"
        )
    if entidad_tipo == "feature_query":
        row = db.get(ProjectRecord, entidad_id)
        if row is None or row.record_type != "query":
            raise HTTPException(status_code=404, detail="Consulta no encontrada")
        return row.project_id
    if entidad_tipo == "feature_report":
        row = db.get(ProjectRecord, entidad_id)
        if row is None or row.record_type != "report":
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        return row.project_id
    row = db.get(ProjectRecord, entidad_id)
    if row is not None and row.record_type == entidad_tipo:
        return row.project_id
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
    if entidad_tipo == "hub_entry":
        row = db.get(HubEntry, entidad_id)
        if not row:
            raise HTTPException(status_code=404, detail="Entrada no encontrada")
        return row.project_id
    if entidad_tipo == "project":
        row = db.get(Project, entidad_id)
        if not row:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")
        return row.id
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


def assert_attachment_author_or_pm(
    db: Session,
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    *,
    uploaded_by: uuid.UUID,
) -> None:
    """PATCH/DELETE adjunto: autor o quien puede gestionar documentos del proyecto."""
    from app.domain.capabilities import HUB_DOCUMENT_EDIT, PROJECT_SETTINGS_EDIT
    from app.services.workflow.authorize import assert_any_capability

    if actor_user_id == uploaded_by:
        return
    assert_any_capability(
        db,
        project_id,
        actor_user_id,
        [HUB_DOCUMENT_EDIT, PROJECT_SETTINGS_EDIT],
        detail="Solo el autor o un gestor del proyecto puede modificar este adjunto",
    )


def list_exposures_for_viewer(
    db: Session,
    project_id: uuid.UUID,
    *,
    viewer_user_id: uuid.UUID | None,
    record_id: uuid.UUID | None = None,
) -> list[DocumentExposure]:
    from app.domain.capabilities import DOCUMENT_VIEW_INTERNAL
    from app.services.workflow.capabilities import user_has_capability

    stmt = select(DocumentExposure).where(DocumentExposure.project_id == project_id)
    if record_id is not None:
        stmt = stmt.where(DocumentExposure.record_id == record_id)
    exposures = list(db.scalars(stmt.order_by(DocumentExposure.created_at.desc())))
    if viewer_user_id is None or user_has_capability(
        db, project_id, viewer_user_id, DOCUMENT_VIEW_INTERNAL
    ):
        return exposures
    filtered: list[DocumentExposure] = []
    for exp in exposures:
        if exp.document_id is not None:
            doc = db.get(Document, exp.document_id)
            if doc and doc.visibilidad == "interno":
                continue
        filtered.append(exp)
    return filtered


def resolve_audit_logs_for_user(
    db: Session,
    logs: list[AuditLog],
    *,
    project_id: uuid.UUID,
    viewer_user_id: uuid.UUID | None,
) -> list[AuditLog]:
    from app.services.workflow.visibility import filter_audit_logs_for_capabilities

    return filter_audit_logs_for_capabilities(
        db,
        logs,
        project_id=project_id,
        viewer_user_id=viewer_user_id,
    )


def document_visible_for_user(
    db: Session,
    document: Document,
    *,
    viewer_user_id: uuid.UUID | None,
) -> bool:
    from app.services.workflow.visibility import document_visible_to_capabilities

    return document_visible_to_capabilities(
        db,
        document.project_id,
        viewer_user_id,
        document.visibilidad,
    )


def hub_entry_visible_for_user(
    db: Session,
    entry: HubEntry,
    *,
    viewer_user_id: uuid.UUID | None,
) -> bool:
    from app.services.workflow.visibility import hub_entry_visible_to_capabilities

    return hub_entry_visible_to_capabilities(
        db,
        entry.project_id,
        viewer_user_id,
        entry.visibilidad,
    )
