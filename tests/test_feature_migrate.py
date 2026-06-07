"""Tests migración de feature entre hitos (§4.5)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import AuditLog, Feature, Milestone, Project, ProjectMember, User
from app.services.features import migrate_feature


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def api_client(db_session: Session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _seed(session: Session):
    pm_id = uuid4()
    session.add(
        User(id=pm_id, nombre="PM", email="pm@mig.test", password_hash="x")
    )
    project = Project(
        id=uuid4(),
        nombre="P",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.add(ProjectMember(project_id=project.id, user_id=pm_id, rol="pm"))
    h1 = Milestone(
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
    h2 = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H2",
        tipo="entrega",
        orden=2,
        fecha_inicio=date(2026, 7, 1),
        fecha_fin=date(2026, 12, 31),
        estado="pendiente",
        created_by=pm_id,
    )
    session.add_all([h1, h2])
    feature = Feature(
        id=uuid4(),
        milestone_id=h1.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        estado="en_progreso",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(feature)
    session.commit()
    return project, h1, h2, feature, pm_id


def test_migrar_desarrollo_entre_hitos(db_session: Session):
    project, h1, h2, feature, pm_id = _seed(db_session)

    migrate_feature(
        db_session,
        feature,
        project,
        h1,
        h2,
        actor_user_id=pm_id,
    )
    db_session.commit()

    assert feature.milestone_id == h2.id
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.entidad_id == feature.id,
            AuditLog.accion == "migrada",
            AuditLog.campo == "milestone_id",
        )
    )
    assert audit is not None
    assert audit.valor_anterior == str(h1.id)
    assert audit.valor_nuevo == str(h2.id)


def test_migrar_bug_falla(db_session: Session):
    project, h1, h2, feature, pm_id = _seed(db_session)
    feature.tipo = "bug"
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        migrate_feature(
            db_session,
            feature,
            project,
            h1,
            h2,
            actor_user_id=pm_id,
        )
    assert exc.value.status_code == 409


def test_migrar_a_hito_cancelado_falla(db_session: Session):
    project, h1, h2, feature, pm_id = _seed(db_session)
    h2.estado = "cancelado"
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        migrate_feature(
            db_session,
            feature,
            project,
            h1,
            h2,
            actor_user_id=pm_id,
        )
    assert exc.value.status_code == 409


def test_migrate_api(db_session: Session, api_client: TestClient):
    project, h1, h2, feature, pm_id = _seed(db_session)

    response = api_client.post(
        f"/api/v1/projects/{project.id}/milestones/{h1.id}/features/{feature.id}/migrate",
        json={
            "actor_user_id": str(pm_id),
            "target_milestone_id": str(h2.id),
        },
    )
    assert response.status_code == 200
    assert response.json()["milestone_id"] == str(h2.id)
