"""Tests del endpoint GET /projects/pm-portfolio."""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import (
    AuditLog,
    Feature,
    FeatureQuery,
    FeatureReport,
    Milestone,
    OrganizationMember,
    ProjectMember,
    User,
)
from app.services.auth_tokens import create_access_token
from app.services.project_bundle import build_project_bundle
from tests.org_helpers import create_organization, create_project_for_org, create_user


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


def _auth_headers(user_id, org_id):
    token = create_access_token(user_id=user_id, organization_id=org_id)
    return {"Authorization": f"Bearer {token}"}


def _seed_feature_graph(session: Session, project, pm_id):
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(milestone)
    session.flush()

    completed = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="F done",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 2, 1),
        estado="completado",
        created_by=pm_id,
    )
    in_progress = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="F wip",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 2, 1),
        estado="en_progreso",
        bloqueada=True,
        created_by=pm_id,
    )
    release = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="F release",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 2, 1),
        estado="esperando_liberacion_pm",
        created_by=pm_id,
    )
    session.add_all([completed, in_progress, release])
    session.flush()

    session.add(
        FeatureReport(
            id=uuid4(),
            feature_id=completed.id,
            reported_by=pm_id,
            tipo="bug",
            descripcion="Bug pendiente",
            estado="pendiente",
        )
    )
    session.add(
        FeatureQuery(
            id=uuid4(),
            feature_id=in_progress.id,
            titulo="Consulta",
            descripcion="Pendiente PM",
            estado="esperando_pm",
            created_by=pm_id,
        )
    )
    session.flush()
    return milestone


def test_pm_portfolio_two_projects(api_client: TestClient, db_session: Session):
    pm = create_user(db_session, email="pm@portfolio.test")
    org = create_organization(db_session, owner_id=pm.id)
    p1 = create_project_for_org(db_session, pm.id, org, nombre="Alpha")
    p2 = create_project_for_org(db_session, pm.id, org, nombre="Beta")
    _seed_feature_graph(db_session, p1, pm.id)
    db_session.commit()

    res = api_client.get(
        f"/api/v1/projects/pm-portfolio?organization_id={org.id}",
        headers=_auth_headers(pm.id, org.id),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["organizationId"] == str(org.id)
    assert len(data["projects"]) == 2
    names = {p["nombre"] for p in data["projects"]}
    assert names == {"Alpha", "Beta"}

    alpha = next(p for p in data["projects"] if p["nombre"] == "Alpha")
    assert alpha["milestoneCount"] == 1
    assert alpha["featuresTotal"] == 3
    assert alpha["featuresCompleted"] == 1
    assert alpha["featuresInProgress"] == 1
    assert alpha["featuresBlocked"] == 1
    assert alpha["progressPct"] == 33
    assert alpha["inboxActionCount"] == 3  # 1 report + 1 query + 1 release
    assert alpha["inboxBreakdown"] == {
        "pendingReports": 1,
        "pendingQueries": 1,
        "pendingReleases": 1,
    }
    assert alpha["health"] == "at_risk"
    assert "bandeja_pendiente" in alpha["healthReasons"]
    assert "features_bloqueadas" in alpha["healthReasons"]
    assert alpha["featuresPending"] == 0
    assert alpha["isStalled"] is False

    assert len(data["attentionItems"]) == 3
    attention_projects = {item["projectNombre"] for item in data["attentionItems"]}
    assert attention_projects == {"Alpha"}
    attention_kinds = {item["kind"] for item in data["attentionItems"]}
    assert attention_kinds == {"report", "query", "release"}

    assert data["totals"]["activeProjects"] == 2
    assert data["totals"]["inboxTotal"] == 3
    assert data["totals"]["needsAttention"] == 1
    assert data["totals"]["atRiskCount"] == 1
    assert data["totals"]["overdueCount"] == 0
    assert data["totals"]["blockedTotal"] == 1
    assert data["totals"]["inboxBreakdown"] == {
        "pendingReports": 1,
        "pendingQueries": 1,
        "pendingReleases": 1,
    }


def test_pm_portfolio_no_pm_role_returns_empty(
    api_client: TestClient, db_session: Session
):
    pm = create_user(db_session, email="pm@owner.test")
    dev = create_user(db_session, email="dev@portfolio.test")
    org = create_organization(db_session, owner_id=pm.id)
    project = create_project_for_org(db_session, pm.id, org)
    db_session.add(
        OrganizationMember(organization_id=org.id, user_id=dev.id, rol="member")
    )
    db_session.add(
        ProjectMember(project_id=project.id, user_id=dev.id, rol="dev")
    )
    db_session.commit()

    res = api_client.get(
        f"/api/v1/projects/pm-portfolio?organization_id={org.id}",
        headers=_auth_headers(dev.id, org.id),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["projects"] == []
    assert data["totals"]["activeProjects"] == 0
    assert data["totals"]["atRiskCount"] == 0
    assert data["totals"]["overdueCount"] == 0


def test_pm_portfolio_non_org_member_forbidden(
    api_client: TestClient, db_session: Session
):
    pm = create_user(db_session, email="pm@forbidden.test")
    outsider = create_user(db_session, email="outsider@test")
    org = create_organization(db_session, owner_id=pm.id)
    create_project_for_org(db_session, pm.id, org)
    db_session.commit()

    res = api_client.get(
        f"/api/v1/projects/pm-portfolio?organization_id={org.id}",
        headers=_auth_headers(outsider.id, org.id),
    )
    assert res.status_code == 403


def test_pm_portfolio_health_overdue(api_client: TestClient, db_session: Session):
    pm = create_user(db_session, email="pm@overdue.test")
    org = create_organization(db_session, owner_id=pm.id)
    create_project_for_org(
        db_session,
        pm.id,
        org,
        nombre="Vencido",
        fecha_inicio=date(2019, 1, 1),
        fecha_fin=date(2020, 1, 1),
    )
    db_session.commit()

    res = api_client.get(
        f"/api/v1/projects/pm-portfolio?organization_id={org.id}",
        headers=_auth_headers(pm.id, org.id),
    )
    assert res.status_code == 200
    project = res.json()["projects"][0]
    assert project["health"] == "overdue"
    assert project["daysOverdue"] > 0
    assert project["daysRemaining"] is None
    assert "fecha_vencida" in project["healthReasons"]
    assert res.json()["totals"]["overdueCount"] == 1


def test_pm_portfolio_health_closed(api_client: TestClient, db_session: Session):
    pm = create_user(db_session, email="pm@closed.test")
    org = create_organization(db_session, owner_id=pm.id)
    create_project_for_org(
        db_session,
        pm.id,
        org,
        nombre="Cerrado",
        estado="cerrado",
    )
    db_session.commit()

    res = api_client.get(
        f"/api/v1/projects/pm-portfolio?organization_id={org.id}",
        headers=_auth_headers(pm.id, org.id),
    )
    assert res.status_code == 200
    project = res.json()["projects"][0]
    assert project["health"] == "closed"
    assert project["inboxBreakdown"] == {
        "pendingReports": 0,
        "pendingQueries": 0,
        "pendingReleases": 0,
    }


def test_inbox_action_count_matches_bundle(db_session: Session):
    pm = create_user(db_session, email="pm@bundle.test")
    org = create_organization(db_session, owner_id=pm.id)
    project = create_project_for_org(db_session, pm.id, org)
    _seed_feature_graph(db_session, project, pm.id)
    db_session.commit()

    bundle = build_project_bundle(db_session, project)
    from app.services.pm_portfolio import build_pm_portfolio

    portfolio = build_pm_portfolio(db_session, org.id, pm.id)
    summary = portfolio.projects[0]
    assert summary.inbox_action_count == bundle.inbox_action_count
    assert summary.inbox_breakdown.pending_reports == 1
    assert summary.inbox_breakdown.pending_queries == 1
    assert summary.inbox_breakdown.pending_releases == 1


def test_pm_portfolio_recent_activity(api_client: TestClient, db_session: Session):
    pm = create_user(db_session, email="pm@activity.test")
    org = create_organization(db_session, owner_id=pm.id)
    project = create_project_for_org(db_session, pm.id, org, nombre="Activo")
    milestone = _seed_feature_graph(db_session, project, pm.id)
    db_session.add(
        AuditLog(
            id=uuid4(),
            project_id=project.id,
            user_id=pm.id,
            entidad_tipo="feature",
            entidad_id=milestone.id,
            accion="estado_changed",
            campo="estado",
            valor_anterior="pendiente",
            valor_nuevo="en_progreso",
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    res = api_client.get(
        f"/api/v1/projects/pm-portfolio?organization_id={org.id}",
        headers=_auth_headers(pm.id, org.id),
    )
    assert res.status_code == 200
    activity = res.json()["recentActivity"]
    assert len(activity) == 1
    assert activity[0]["projectNombre"] == "Activo"
    assert activity[0]["accion"] == "estado_changed"


def test_pm_portfolio_critical_milestones(api_client: TestClient, db_session: Session):
    pm = create_user(db_session, email="pm@milestones.test")
    org = create_organization(db_session, owner_id=pm.id)
    project = create_project_for_org(db_session, pm.id, org, nombre="Hitos")
    soon = date.today() + timedelta(days=5)
    db_session.add(
        Milestone(
            id=uuid4(),
            project_id=project.id,
            nombre="H critico",
            tipo="entrega",
            orden=1,
            fecha_inicio=date.today(),
            fecha_fin=soon,
            estado="en_progreso",
            created_by=pm.id,
        )
    )
    db_session.commit()

    res = api_client.get(
        f"/api/v1/projects/pm-portfolio?organization_id={org.id}",
        headers=_auth_headers(pm.id, org.id),
    )
    assert res.status_code == 200
    milestones = res.json()["criticalMilestones"]
    assert len(milestones) == 1
    assert milestones[0]["nombre"] == "H critico"
    assert milestones[0]["projectNombre"] == "Hitos"
    assert milestones[0]["daysRemaining"] == 5


def test_pm_portfolio_stalled_project(api_client: TestClient, db_session: Session):
    pm = create_user(db_session, email="pm@stalled.test")
    org = create_organization(db_session, owner_id=pm.id)
    project = create_project_for_org(db_session, pm.id, org, nombre="Estancado")
    project.created_at = datetime.now(timezone.utc) - timedelta(days=20)
    db_session.commit()

    res = api_client.get(
        f"/api/v1/projects/pm-portfolio?organization_id={org.id}",
        headers=_auth_headers(pm.id, org.id),
    )
    assert res.status_code == 200
    stalled = next(p for p in res.json()["projects"] if p["nombre"] == "Estancado")
    assert stalled["isStalled"] is True
