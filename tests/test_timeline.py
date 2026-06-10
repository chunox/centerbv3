"""Tests timeline unificado (§4.12, §7.1)."""

from datetime import date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    AuditLog,
    Comment,
    Feature,
    Milestone,
    Project,
    ProjectMember,
    User,
)
from app.services.audit import record_audit_log
from app.services.timeline import build_project_timeline
from tests.org_helpers import add_member_with_slug, create_organization


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
    session.add(project)
    add_member_with_slug(session, project, pm_id, 'pm')
    h1 = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        estado="en_progreso",
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
        fecha_inicio=date(2026, 2, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(feature)
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
