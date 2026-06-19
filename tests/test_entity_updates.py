"""Tests PATCH campos descriptivos — proyecto, hito, feature (§4.2, §4.4, §4.5)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import AuditLog, User
from app.schemas.features import FeatureUpdate
from app.schemas.milestones import MilestoneUpdate
from app.schemas.projects import ProjectUpdate
from app.services.features import update_feature
from app.services.milestones import update_milestone
from app.services.projects import apply_project_estado_action, update_project
from app.services.records.repository import create_record, get_field
from tests.org_helpers import create_organization, create_project_for_org
from tests.record_helpers import create_feature_record, create_milestone_record


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_project(session: Session):
    pm_id = uuid4()
    session.add(
        User(id=pm_id, nombre="PM", email="pm@patch.test", password_hash="x")
    )
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(session, pm_id, org, nombre="Original")
    project.descripcion = "Desc"
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_feature_record(
        session, project, milestone, created_by=pm_id, with_default_task=False
    )
    session.commit()
    return project, milestone, feature, pm_id


def test_update_project_nombre_y_audit(db_session: Session):
    project, _, _, pm_id = _seed_project(db_session)

    update_project(
        db_session,
        project,
        ProjectUpdate(nombre="Renombrado"),
        actor_user_id=pm_id,
    )
    db_session.commit()

    assert project.nombre == "Renombrado"
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entidad_tipo == "project",
            AuditLog.campo == "nombre",
            AuditLog.accion == "updated",
        )
    )
    assert audit is not None
    assert audit.valor_nuevo == "Renombrado"


def test_update_project_cerrado_falla(db_session: Session):
    project, _, _, pm_id = _seed_project(db_session)
    apply_project_estado_action(
        db_session, project, action="cerrar", actor_user_id=pm_id
    )

    with pytest.raises(HTTPException) as exc:
        update_project(
            db_session,
            project,
            ProjectUpdate(nombre="X"),
            actor_user_id=pm_id,
        )
    assert exc.value.status_code == 409


def test_update_project_fechas_invalidas(db_session: Session):
    project, _, _, pm_id = _seed_project(db_session)

    with pytest.raises(HTTPException) as exc:
        update_project(
            db_session,
            project,
            ProjectUpdate(
                fecha_inicio=date(2026, 12, 1),
                fecha_fin=date(2026, 1, 1),
            ),
            actor_user_id=pm_id,
        )
    assert exc.value.status_code == 422


def test_update_milestone_manual_estado_blocked_by_workflow(db_session: Session):
    project, milestone, _, pm_id = _seed_project(db_session)

    with pytest.raises(HTTPException) as exc:
        update_milestone(
            db_session,
            milestone,
            project,
            MilestoneUpdate(actor_user_id=pm_id, estado="en_progreso"),
        )
    assert exc.value.status_code == 422
    assert "workflow" in str(exc.value.detail).lower()


def test_update_milestone_cancelado_falla(db_session: Session):
    project, milestone, _, pm_id = _seed_project(db_session)
    milestone.estado = "cancelado"
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        update_milestone(
            db_session,
            milestone,
            project,
            MilestoneUpdate(actor_user_id=pm_id, nombre="X"),
        )
    assert exc.value.status_code == 409


def test_update_feature_prioridad(db_session: Session):
    project, _, feature, pm_id = _seed_project(db_session)

    update_feature(
        db_session,
        feature,
        project,
        FeatureUpdate(actor_user_id=pm_id, prioridad="alta"),
    )
    db_session.commit()

    assert get_field(feature, "prioridad") == "alta"


def test_update_feature_mejora_sin_duracion_falla(db_session: Session):
    project, milestone, _, pm_id = _seed_project(db_session)
    mejora = create_record(
        db_session,
        project,
        entity_type="feature",
        titulo="Export",
        created_by=pm_id,
        parent_id=milestone.id,
        data={
            "tipo": "mejora",
            "prioridad": "media",
            "duracion_estimada": 10,
            "bloqueada": False,
        },
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        update_feature(
            db_session,
            mejora,
            project,
            FeatureUpdate(actor_user_id=pm_id, duracion_estimada=None),
        )
    assert exc.value.status_code == 422
