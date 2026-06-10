"""Tests aprobación/rechazo de reportes (§4.7)."""

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import Feature
from app.models.entities import (
    Feature,
    FeatureReport,
    Milestone,
    Notification,
    Project,
    ProjectMember,
    User,
)
from app.services.feature_reports import apply_report_action
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


def _seed_con_cliente(session: Session, *, fecha_fin_milestone: date):
    pm_id = uuid4()
    cliente_id = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@rep.test", password_hash="x"),
            User(
                id=cliente_id,
                nombre="Cli",
                email="cli@rep.test",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
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
    session.add(project)
    add_member_with_slug(session, project, pm_id, 'pm')
    add_member_with_slug(session, project, cliente_id, 'cliente')
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=fecha_fin_milestone,
        created_by=pm_id,
    )
    session.add(milestone)
    original = Feature(
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
    session.add(original)
    session.commit()
    return project, milestone, original, pm_id, cliente_id


def test_aprobar_reporte_bug_crea_feature(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Botón roto",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    generated = apply_report_action(
        db_session,
        report,
        original,
        project,
        milestone,
        action="aprobar",
        actor_user_id=pm_id,
    )
    assert report.estado == "aprobado"
    assert generated is not None
    assert generated.tipo == "bug"
    assert generated.origen_feature_id == original.id
    assert generated.origen_report_id == report.id
    assert report.generated_feature_id == generated.id
    assert milestone.estado == "en_progreso_con_bug"


def test_aprobar_reporte_mejora_extiende_hito(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    fin_antes = milestone.fecha_fin
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="mejora",
        descripcion="Export Excel",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    generated = apply_report_action(
        db_session,
        report,
        original,
        project,
        milestone,
        action="aprobar",
        actor_user_id=pm_id,
        duracion_estimada=10,
    )
    assert generated is not None
    assert generated.tipo == "mejora"
    assert generated.duracion_estimada == 10
    assert milestone.fecha_fin == fin_antes + timedelta(days=10)


def test_rechazar_reporte(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="No aplica",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    result = apply_report_action(
        db_session,
        report,
        original,
        project,
        milestone,
        action="rechazar",
        actor_user_id=pm_id,
    )
    assert result is None
    assert report.estado == "rechazado"
    notif = db_session.scalar(
        select(Notification).where(
            Notification.user_id == cliente_id,
            Notification.tipo == "reporte_resuelto",
        )
    )
    assert notif is not None


def test_aprobar_mejora_sin_duracion_falla(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="mejora",
        descripcion="Sin días",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        apply_report_action(
            db_session,
            report,
            original,
            project,
            milestone,
            action="aprobar",
            actor_user_id=pm_id,
        )
    assert exc.value.status_code == 422


@pytest.fixture
def api_client(db_session: Session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_inbox_lista_pendientes_con_contexto(db_session: Session, api_client: TestClient):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Crash al guardar",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    response = api_client.get(
        f"/api/v1/projects/{project.id}/feature-reports",
        params={"estado": "pendiente"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    item = data[0]
    assert item["id"] == str(report.id)
    assert item["feature_nombre"] == "Login"
    assert item["milestone_id"] == str(milestone.id)
    assert item["feature_estado"] == "completado"


def test_inbox_filtra_por_reported_by(db_session: Session, api_client: TestClient):
    project, _, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    otro_cliente = uuid4()
    db_session.add(
        User(id=otro_cliente, nombre="Otro", email="otro@rep.test", password_hash="x")
    )
    db_session.add_all(
        [
            FeatureReport(
                id=uuid4(),
                feature_id=original.id,
                reported_by=cliente_id,
                tipo="bug",
                descripcion="Mío",
                estado="pendiente",
            ),
            FeatureReport(
                id=uuid4(),
                feature_id=original.id,
                reported_by=otro_cliente,
                tipo="mejora",
                descripcion="Ajeno",
                estado="pendiente",
            ),
        ]
    )
    db_session.commit()

    response = api_client.get(
        f"/api/v1/projects/{project.id}/feature-reports",
        params={"reported_by": str(cliente_id)},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["descripcion"] == "Mío"


def test_inbox_action_aprobar_bug(db_session: Session, api_client: TestClient):
    project, _, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Botón roto",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    response = api_client.post(
        f"/api/v1/projects/{project.id}/feature-reports/{report.id}/actions",
        json={"action": "aprobar", "actor_user_id": str(pm_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["estado"] == "aprobado"
    assert body["generated_feature_id"] is not None
    generated = db_session.get(Feature, UUID(body["generated_feature_id"]))
    assert generated is not None
    assert generated.tipo == "bug"
