"""Tests guards de acceso alineados con INTERACCIONES_APP (§4, §14)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    Feature,
    FeatureQuery,
    Milestone,
    Project,
    ProjectMember,
    Task,
    User,
)
from app.services.features import apply_feature_action, ensure_default_task
from tests.org_helpers import add_member_with_slug, create_organization


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


def _seed_interno_blocked(session: Session):
    pm_id = uuid4()
    dev_id = uuid4()
    qa_id = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@guard.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@guard.test", password_hash="x"),
            User(id=qa_id, nombre="QA", email="qa@guard.test", password_hash="x"),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="Guard",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    add_member_with_slug(session, project, pm_id, 'pm')
    add_member_with_slug(session, project, dev_id, 'dev')
    add_member_with_slug(session, project, qa_id, 'qa')
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        created_by=pm_id,
    )
    session.add(milestone)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        estado="uat",
        bloqueada=True,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(feature)
    ensure_default_task(session, feature, created_by=pm_id)
    task = session.query(Task).filter(Task.feature_id == feature.id).one()
    task.estado = "ready_for_test"
    session.add(
        FeatureQuery(
            feature_id=feature.id,
            titulo="Consulta",
            descripcion="Bloqueo",
            estado="esperando_pm",
            created_by=dev_id,
        )
    )
    session.commit()
    return project, milestone, feature, pm_id, dev_id, qa_id


def test_bloqueada_impide_enviar_al_pm(db_session: Session):
    project, _, feature, _, _, qa_id = _seed_interno_blocked(db_session)
    with pytest.raises(HTTPException) as exc:
        apply_feature_action(
            db_session,
            feature,
            project,
            action="enviar_al_pm",
            actor_user_id=qa_id,
        )
    assert exc.value.status_code == 409


def test_bloqueada_permite_cancelar(db_session: Session):
    project, _, feature, pm_id, _, _ = _seed_interno_blocked(db_session)
    apply_feature_action(
        db_session,
        feature,
        project,
        action="cancelar",
        actor_user_id=pm_id,
    )
    assert feature.estado == "cancelado"


def test_create_milestone_en_proyecto_cerrado_falla(
    db_session: Session, api_client: TestClient
):
    pm_id = uuid4()
    db_session.add(
        User(id=pm_id, nombre="PM", email="pm@closed.test", password_hash="x")
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="Cerrado",
        tipo="interno",
        estado="cerrado",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    db_session.add(project)
    add_member_with_slug(db_session, project, pm_id, 'pm')
    db_session.commit()

    response = api_client.post(
        f"/api/v1/projects/{project.id}/milestones",
        json={
            "nombre": "H2",
            "tipo": "entrega",
            "orden": 2,
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-12-31",
            "created_by": str(pm_id),
        },
    )
    assert response.status_code == 409


def test_create_feature_sin_rol_pm_falla(db_session: Session, api_client: TestClient):
    pm_id = uuid4()
    dev_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@feat.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@feat.test", password_hash="x"),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="P",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    db_session.add(project)
    add_member_with_slug(db_session, project, pm_id, 'pm')
    add_member_with_slug(db_session, project, dev_id, 'dev')
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        created_by=pm_id,
    )
    db_session.add(milestone)
    db_session.commit()

    response = api_client.post(
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}/features",
        json={
            "nombre": "Nueva",
            "tipo": "desarrollo",
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-03-31",
            "created_by": str(dev_id),
        },
    )
    assert response.status_code == 403


def test_reporte_solo_cliente(db_session: Session, api_client: TestClient):
    pm_id = uuid4()
    cliente_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@rep2.test", password_hash="x"),
            User(
                id=cliente_id,
                nombre="Cli",
                email="cli@rep2.test",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="CC",
        tipo="con_cliente",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    db_session.add(project)
    add_member_with_slug(db_session, project, pm_id, 'pm')
    add_member_with_slug(db_session, project, cliente_id, 'cliente')
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        created_by=pm_id,
    )
    db_session.add(milestone)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        estado="completado",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    db_session.add(feature)
    db_session.commit()

    pm_report = api_client.post(
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}/features/{feature.id}/reports",
        json={
            "reported_by": str(pm_id),
            "tipo": "bug",
            "descripcion": "PM no puede",
        },
    )
    assert pm_report.status_code == 403

    ok = api_client.post(
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}/features/{feature.id}/reports",
        json={
            "reported_by": str(cliente_id),
            "tipo": "bug",
            "descripcion": "Cliente sí",
        },
    )
    assert ok.status_code == 201


def test_adjunto_patch_solo_autor_o_pm(db_session: Session, api_client: TestClient):
    pm_id = uuid4()
    dev_id = uuid4()
    other_dev = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@att.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@att.test", password_hash="x"),
            User(
                id=other_dev,
                nombre="Dev2",
                email="dev2@att.test",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="P",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    db_session.add(project)
    add_member_with_slug(db_session, project, pm_id, 'pm')
    add_member_with_slug(db_session, project, dev_id, 'dev')
    add_member_with_slug(db_session, project, other_dev, 'dev')
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        created_by=pm_id,
    )
    db_session.add(milestone)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        estado="pendiente",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    db_session.add(feature)
    db_session.commit()

    created = api_client.post(
        "/api/v1/attachments",
        json={
            "url": "https://example.com/a.pdf",
            "nombre_original": "a.pdf",
            "mime_type": "application/pdf",
            "tamano_bytes": 10,
            "uploaded_by": str(dev_id),
            "entidad_tipo": "feature",
            "entidad_id": str(feature.id),
        },
    )
    assert created.status_code == 201
    att_id = created.json()["id"]

    forbidden = api_client.patch(
        f"/api/v1/attachments/{att_id}",
        json={
            "actor_user_id": str(other_dev),
            "nombre_original": "hack.pdf",
        },
    )
    assert forbidden.status_code == 403

    allowed = api_client.patch(
        f"/api/v1/attachments/{att_id}",
        json={
            "actor_user_id": str(pm_id),
            "nombre_original": "renombrado.pdf",
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["nombre_original"] == "renombrado.pdf"
