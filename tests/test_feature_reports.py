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
from app.models.entities import Notification, ProjectRecord, User
from app.services.feature_reports import apply_report_action
from app.services.records.repository import create_record, get_field
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org
from tests.record_helpers import create_milestone_record, create_report_record


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
    project = create_project_for_org(
        session, pm_id, org, nombre="CC", tipo="con_cliente"
    )
    add_member_with_slug(session, project, cliente_id, "cliente")
    milestone = create_milestone_record(session, project, created_by=pm_id)
    milestone.fecha_fin = fecha_fin_milestone
    original = create_record(
        session,
        project,
        entity_type="feature",
        titulo="Login",
        created_by=pm_id,
        parent_id=milestone.id,
        estado="completado",
        data={"tipo": "desarrollo", "prioridad": "media", "bloqueada": False},
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
    )
    session.commit()
    return project, milestone, original, pm_id, cliente_id


def _report(
    session: Session,
    project,
    feature: ProjectRecord,
    *,
    reported_by: UUID,
    tipo: str,
    descripcion: str,
) -> ProjectRecord:
    return create_report_record(
        session,
        project,
        feature,
        reported_by=reported_by,
        tipo=tipo,
        descripcion=descripcion,
    )


def test_aprobar_reporte_bug_crea_feature(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = _report(
        db_session,
        project,
        original,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Botón roto",
    )
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
    assert get_field(generated, "tipo") == "bug"
    assert get_field(generated, "origen_feature_id") == str(original.id)
    assert get_field(generated, "origen_report_id") == str(report.id)
    assert get_field(report, "generated_feature_id") == str(generated.id)
    assert milestone.estado == "en_progreso_con_bug"


def test_aprobar_reporte_mejora_extiende_hito(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    fin_antes = milestone.fecha_fin
    report = _report(
        db_session,
        project,
        original,
        reported_by=cliente_id,
        tipo="mejora",
        descripcion="Export Excel",
    )
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
    assert get_field(generated, "tipo") == "mejora"
    assert get_field(generated, "duracion_estimada") == 10
    assert milestone.fecha_fin == fin_antes + timedelta(days=10)


def test_rechazar_reporte(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = _report(
        db_session,
        project,
        original,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="No aplica",
    )
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
    report = _report(
        db_session,
        project,
        original,
        reported_by=cliente_id,
        tipo="mejora",
        descripcion="Sin días",
    )
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
    report = _report(
        db_session,
        project,
        original,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Crash al guardar",
    )
    db_session.commit()

    response = api_client.get(
        f"/api/v1/projects/{project.id}/records",
        params={"record_type": "report", "actor_user_id": str(pm_id)},
    )
    assert response.status_code == 200
    data = [r for r in response.json() if r["estado"] == "pendiente"]
    assert len(data) == 1
    item = data[0]
    assert item["id"] == str(report.id)
    assert item["descripcion"] == "Crash al guardar"
    assert item["parent_id"] == str(original.id)


def test_inbox_filtra_por_reported_by(db_session: Session, api_client: TestClient):
    project, _, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    otro_cliente = uuid4()
    db_session.add(
        User(id=otro_cliente, nombre="Otro", email="otro@rep.test", password_hash="x")
    )
    _report(
        db_session,
        project,
        original,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Mío",
    )
    _report(
        db_session,
        project,
        original,
        reported_by=otro_cliente,
        tipo="mejora",
        descripcion="Ajeno",
    )
    db_session.commit()

    response = api_client.get(
        f"/api/v1/projects/{project.id}/records",
        params={"record_type": "report", "actor_user_id": str(pm_id)},
    )
    assert response.status_code == 200
    mine = [
        r
        for r in response.json()
        if (r.get("data") or {}).get("reported_by") == str(cliente_id)
    ]
    assert len(mine) == 1
    assert mine[0]["descripcion"] == "Mío"


def test_inbox_action_aprobar_bug(db_session: Session, api_client: TestClient):
    project, _, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = _report(
        db_session,
        project,
        original,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Botón roto",
    )
    db_session.commit()

    response = api_client.post(
        f"/api/v1/projects/{project.id}/records/{report.id}/transition",
        json={"action_id": "aprobar", "actor_user_id": str(pm_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["estado"] == "aprobado"
    gen_id = (body.get("data") or {}).get("generated_feature_id")
    assert gen_id is not None
    generated = db_session.get(ProjectRecord, UUID(gen_id))
    assert generated is not None
    assert get_field(generated, "tipo") == "bug"
