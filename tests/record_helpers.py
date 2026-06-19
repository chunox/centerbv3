"""Helpers para tests con project_records."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord, User
from app.services.features import ensure_default_task
from app.services.packs import seed_project_from_pack
from app.services.records.repository import create_record
from app.domain.project_templates import get_template
from tests.org_helpers import add_member_with_slug, create_organization


def seed_project_with_roles(
    session: Session,
    *,
    tipo: str = "interno",
    template_slug: str = "t3_interno_clasico",
) -> tuple[Project, uuid.UUID, uuid.UUID, uuid.UUID]:
    pm_id = uuid.uuid4()
    dev_id = uuid.uuid4()
    qa_id = uuid.uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email=f"pm-{pm_id.hex[:6]}@wf.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email=f"dev-{dev_id.hex[:6]}@wf.test", password_hash="x"),
            User(id=qa_id, nombre="QA", email=f"qa-{qa_id.hex[:6]}@wf.test", password_hash="x"),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid.uuid4(),
        nombre="WF",
        template_slug=template_slug,
        pack_slug="software",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.flush()
    seed_project_from_pack(session, project, "software", template_slug=template_slug)
    add_member_with_slug(session, project, pm_id, "pm")
    add_member_with_slug(session, project, dev_id, "dev")
    add_member_with_slug(session, project, qa_id, "qa")
    session.commit()
    return project, pm_id, dev_id, qa_id


def create_milestone_record(
    session: Session,
    project: Project,
    *,
    created_by: uuid.UUID,
    nombre: str = "H1",
    orden: int = 1,
) -> ProjectRecord:
    return create_record(
        session,
        project,
        entity_type="milestone",
        titulo=nombre,
        created_by=created_by,
        data={"tipo": "entrega"},
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        orden=orden,
    )


def create_sprint_record(
    session: Session,
    project: Project,
    *,
    created_by: uuid.UUID,
    nombre: str = "Sprint 1",
    orden: int = 1,
    sprint_goal: str | None = "Goal",
    horas_planeadas: float | None = None,
) -> ProjectRecord:
    data: dict = {}
    if sprint_goal:
        data["sprint_goal"] = sprint_goal
    if horas_planeadas is not None:
        data["horas_planeadas"] = horas_planeadas
    return create_record(
        session,
        project,
        entity_type="sprint",
        titulo=nombre,
        created_by=created_by,
        data=data,
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 3, 14),
        orden=orden,
    )


def create_feature_record(
    session: Session,
    project: Project,
    milestone: ProjectRecord,
    *,
    created_by: uuid.UUID,
    nombre: str = "Login",
    tipo: str = "desarrollo",
    with_default_task: bool = True,
) -> ProjectRecord:
    feature = create_record(
        session,
        project,
        entity_type="feature",
        titulo=nombre,
        created_by=created_by,
        parent_id=milestone.id,
        data={"tipo": tipo, "prioridad": "media", "bloqueada": False},
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
    )
    if with_default_task:
        ensure_default_task(session, feature, created_by=created_by)
    session.flush()
    return feature


def seed_milestone_feature(
    session: Session,
    project: Project,
    pm_id: uuid.UUID,
) -> tuple[ProjectRecord, ProjectRecord]:
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_feature_record(session, project, milestone, created_by=pm_id)
    session.commit()
    return milestone, feature


def create_query_record(
    session: Session,
    project: Project,
    feature: ProjectRecord,
    *,
    created_by: uuid.UUID,
    titulo: str = "Consulta test",
    descripcion: str = "Detalle",
    estado: str = "borrador",
) -> ProjectRecord:
    return create_record(
        session,
        project,
        entity_type="query",
        titulo=titulo,
        created_by=created_by,
        parent_id=feature.id,
        descripcion=descripcion,
        estado=estado,
    )


def create_report_record(
    session: Session,
    project: Project,
    feature: ProjectRecord,
    *,
    reported_by: uuid.UUID,
    tipo: str = "bug",
    descripcion: str = "Detalle",
    estado: str = "pendiente",
) -> ProjectRecord:
    return create_record(
        session,
        project,
        entity_type="report",
        titulo=f"Reporte {tipo}",
        created_by=reported_by,
        parent_id=feature.id,
        descripcion=descripcion,
        estado=estado,
        data={"tipo": tipo, "reported_by": str(reported_by)},
    )
