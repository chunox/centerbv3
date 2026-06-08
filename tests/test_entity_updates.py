"""Tests PATCH campos descriptivos — proyecto, hito, feature (§4.2, §4.4, §4.5)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import AuditLog, Feature, Milestone, Project, ProjectMember, User
from app.schemas.features import FeatureUpdate
from app.schemas.milestones import MilestoneUpdate
from app.schemas.projects import ProjectUpdate
from app.services.features import update_feature
from app.services.milestones import update_milestone
from app.services.projects import apply_project_estado_action, update_project
from tests.org_helpers import create_organization


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
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="Original",
        descripcion="Desc",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.add(ProjectMember(project_id=project.id, user_id=pm_id, rol="pm"))
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        estado="pendiente",
        created_by=pm_id,
    )
    session.add(milestone)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        prioridad="media",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        estado="pendiente",
        created_by=pm_id,
    )
    session.add(feature)
    session.commit()
    return project, milestone, feature, pm_id


def test_update_project_nombre_y_audit(db_session: Session):
    project, _, _, pm_id = _seed_project(db_session)

    update_project(
        db_session,
        project,
        ProjectUpdate(actor_user_id=pm_id, nombre="Renombrado"),
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
            ProjectUpdate(actor_user_id=pm_id, nombre="X"),
        )
    assert exc.value.status_code == 409


def test_update_project_fechas_invalidas(db_session: Session):
    project, _, _, pm_id = _seed_project(db_session)

    with pytest.raises(HTTPException) as exc:
        update_project(
            db_session,
            project,
            ProjectUpdate(
                actor_user_id=pm_id,
                fecha_inicio=date(2026, 12, 1),
                fecha_fin=date(2026, 1, 1),
            ),
        )
    assert exc.value.status_code == 422


def test_update_milestone_manual_estado(db_session: Session):
    project, milestone, _, pm_id = _seed_project(db_session)

    update_milestone(
        db_session,
        milestone,
        project,
        MilestoneUpdate(actor_user_id=pm_id, estado="en_progreso"),
    )
    db_session.commit()

    assert milestone.estado == "en_progreso"


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

    assert feature.prioridad == "alta"


def test_update_feature_mejora_sin_duracion_falla(db_session: Session):
    project, milestone, _, pm_id = _seed_project(db_session)
    mejora = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Export",
        tipo="mejora",
        prioridad="media",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        duracion_estimada=10,
        estado="pendiente",
        created_by=pm_id,
    )
    db_session.add(mejora)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        update_feature(
            db_session,
            mejora,
            project,
            FeatureUpdate(actor_user_id=pm_id, duracion_estimada=None),
        )
    assert exc.value.status_code == 422
