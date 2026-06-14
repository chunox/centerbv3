"""Tests timeline unificado (§4.12, §7.1)."""

from datetime import date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import AuditLog, Comment, User
from app.services.audit import record_audit_log
from app.services.records.repository import create_record
from app.services.timeline import build_project_timeline
from tests.org_helpers import create_organization, create_project_for_org
from tests.record_helpers import create_milestone_record


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(session: Session):
    pm_id = uuid4()
    session.add(
        User(id=pm_id, nombre="PM", email="pm@tl.test", password_hash="x")
    )
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(session, pm_id, org, nombre="P")
    h1 = create_milestone_record(session, project, created_by=pm_id, nombre="H1", orden=1)
    h1.estado = "en_progreso"
    h2 = create_milestone_record(
        session,
        project,
        created_by=pm_id,
        nombre="H2",
        orden=2,
    )
    h2.fecha_inicio = date(2026, 7, 1)
    h2.fecha_fin = date(2026, 12, 31)
    feature = create_record(
        session,
        project,
        entity_type="feature",
        titulo="Login",
        created_by=pm_id,
        parent_id=h1.id,
        estado="en_progreso",
        data={"tipo": "desarrollo", "prioridad": "media", "bloqueada": False},
        fecha_inicio=date(2026, 2, 1),
        fecha_fin=date(2026, 3, 31),
    )
    session.flush()
    record_audit_log(
        session,
        project_id=project.id,
        user_id=pm_id,
        entidad_tipo="feature",
        entidad_id=feature.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior="pendiente",
        valor_nuevo="en_progreso",
    )
    session.add(
        Comment(
            id=uuid4(),
            entidad_tipo="feature",
            entidad_id=feature.id,
            user_id=pm_id,
            contenido="Avance del login",
            estado_momento="en_progreso",
            created_at=datetime(2026, 2, 15, 10, 0, 0),
        )
    )
    session.commit()
    return project, h1, h2, feature, pm_id


def test_timeline_eventos_y_plan():
    session = _session()
    project, h1, h2, feature, pm_id = _seed(session)

    timeline = build_project_timeline(session, project.id)

    assert len(timeline.plan) == 3
    assert {p.tipo for p in timeline.plan} == {"milestone", "feature"}
    assert len(timeline.eventos) == 2
    sources = {e.source for e in timeline.eventos}
    assert sources == {"audit", "comment"}
    audit = next(e for e in timeline.eventos if e.source == "audit")
    assert audit.feature_nombre == "Login"
    assert audit.milestone_nombre == "H1"
    session.close()


def test_timeline_filtro_milestone():
    session = _session()
    project, h1, h2, feature, _ = _seed(session)

    timeline = build_project_timeline(session, project.id, milestone_id=h2.id)

    assert len(timeline.plan) == 1
    assert timeline.plan[0].nombre == "H2"
    assert len(timeline.eventos) == 0
    session.close()


def test_timeline_api():
    session = _session()
    project, _, _, _, pm_id = _seed(session)

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as client:
        response = client.get(f"/api/v1/projects/{project.id}/timeline")
        assert response.status_code == 200
        body = response.json()
        assert len(body["plan"]) == 3
        assert len(body["eventos"]) == 2
    app.dependency_overrides.clear()
    session.close()
