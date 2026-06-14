"""Tests templates de proyecto y roles extendidos."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.domain.project_templates import PROJECT_TEMPLATES
from app.main import app
from app.models.entities import Project, ProjectMember, ProjectRole, User
from app.services.records.repository import create_record
from tests.record_helpers import create_feature_record, create_milestone_record
from tests.org_helpers import add_member_with_slug, create_organization, create_user


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


def _create_project_payload(org_id, owner_id, template_slug: str) -> dict:
    return {
        "organization_id": str(org_id),
        "nombre": f"Proyecto {template_slug}",
        "template_slug": template_slug,
        "fecha_inicio": "2026-01-01",
        "fecha_fin": "2026-12-31",
        "created_by": str(owner_id),
    }


def test_list_project_templates(api_client: TestClient):
    response = api_client.get("/api/v1/project-templates")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    slugs = {item["slug"] for item in body}
    assert slugs == set(PROJECT_TEMPLATES.keys())


@pytest.mark.parametrize(
    "template_slug,expected_roles,expected_profile,expected_tipo,expected_creator",
    [
        (
            "t1_cliente_clasico",
            {"pm", "tech_lead", "dev", "qa", "cliente"},
            "with_client",
            "con_cliente",
            "pm",
        ),
        (
            "t2_cliente_pm_tecnico",
            {"pm_tecnico", "dev", "qa", "cliente"},
            "with_client",
            "con_cliente",
            "pm_tecnico",
        ),
        (
            "t3_interno_clasico",
            {"pm", "tech_lead", "dev", "qa"},
            "internal",
            "interno",
            "pm",
        ),
        (
            "t4_interno_pm_tecnico",
            {"pm_tecnico", "dev", "qa"},
            "internal",
            "interno",
            "pm_tecnico",
        ),
        (
            "t5_freestyle",
            {"pm", "pm_tecnico", "dev", "tech_lead", "qa", "cliente"},
            "flexible",
            "freestyle",
            "pm",
        ),
    ],
)
def test_create_project_per_template(
    api_client: TestClient,
    db_session: Session,
    template_slug: str,
    expected_roles: set[str],
    expected_profile: str,
    expected_tipo: str,
    expected_creator: str,
):
    owner = create_user(db_session, email=f"own-{template_slug}@test.local")
    org = create_organization(db_session, owner_id=owner.id)
    db_session.commit()

    response = api_client.post(
        "/api/v1/projects",
        json=_create_project_payload(org.id, owner.id, template_slug),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["profile_slug"] == expected_profile
    assert body["tipo"] == expected_tipo
    assert body["template_slug"] == template_slug
    project_id = UUID(body["id"])

    roles = list(
        db_session.scalars(
            select(ProjectRole).where(ProjectRole.project_id == project_id)
        )
    )
    assert {r.slug for r in roles} == expected_roles

    member = db_session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == owner.id,
        )
    )
    assert member is not None
    creator_role = db_session.get(ProjectRole, member.role_id)
    assert creator_role is not None
    assert creator_role.slug == expected_creator


def test_t1_missing_pm_role(api_client: TestClient, db_session: Session):
    owner = create_user(db_session, email="own-t1@test.local")
    org = create_organization(db_session, owner_id=owner.id)
    db_session.commit()

    response = api_client.post(
        "/api/v1/projects",
        json=_create_project_payload(org.id, owner.id, "t2_cliente_pm_tecnico"),
    )
    assert response.status_code == 201
    project_id = UUID(response.json()["id"])
    roles = list(
        db_session.scalars(
            select(ProjectRole).where(ProjectRole.project_id == project_id)
        )
    )
    assert "pm" not in {r.slug for r in roles}


def test_tech_lead_can_create_milestone(api_client: TestClient, db_session: Session):
    owner = create_user(db_session, email="own-tl@test.local")
    tl = create_user(db_session, email="tl@test.local")
    org = create_organization(db_session, owner_id=owner.id)
    db_session.commit()

    created = api_client.post(
        "/api/v1/projects",
        json=_create_project_payload(org.id, owner.id, "t1_cliente_clasico"),
    )
    assert created.status_code == 201
    project_id = UUID(created.json()["id"])
    project = db_session.get(Project, project_id)
    add_member_with_slug(db_session, project, tl.id, "tech_lead")
    db_session.commit()

    response = api_client.post(
        f"/api/v1/projects/{project_id}/records",
        json={
            "actor_user_id": str(tl.id),
            "record_type": "milestone",
            "titulo": "Hito TL",
            "data": {"tipo": "entrega"},
            "orden": 1,
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-06-30",
        },
    )
    assert response.status_code == 201


def test_pm_task_move_requires_kanban_capability(
    db_session: Session, api_client: TestClient
):
    from app.domain.capabilities import KANBAN_TASK_MOVE
    from app.services.role_capabilities import ensure_role_capabilities
    from tests.org_helpers import create_project_for_org

    pm_id = uuid4()
    pm_tecnico_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@move.test", password_hash="x"),
            User(
                id=pm_tecnico_id,
                nombre="PMT",
                email="pmt@move.test",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(
        db_session,
        pm_id,
        org,
        template_slug="t5_freestyle",
    )
    add_member_with_slug(db_session, project, pm_tecnico_id, "pm_tecnico")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        nombre="F1",
        with_default_task=False,
    )
    task = create_record(
        db_session,
        project,
        entity_type="task",
        titulo="T1",
        created_by=pm_tecnico_id,
        parent_id=feature.id,
        estado="backlog",
    )
    db_session.commit()

    pm_move = api_client.post(
        f"/api/v1/projects/{project.id}/records/{task.id}/transition",
        json={
            "actor_user_id": str(pm_id),
            "action_id": "move",
            "target_state": "in_progress",
        },
    )
    assert pm_move.status_code == 403
    assert "kanban.task.move" in pm_move.json()["detail"]

    ensure_role_capabilities(db_session, project.id, "pm", [KANBAN_TASK_MOVE])
    db_session.commit()

    pm_move_ok = api_client.post(
        f"/api/v1/projects/{project.id}/records/{task.id}/transition",
        json={
            "actor_user_id": str(pm_id),
            "action_id": "move",
            "target_state": "in_progress",
        },
    )
    assert pm_move_ok.status_code == 200

    pmt_move = api_client.post(
        f"/api/v1/projects/{project.id}/records/{task.id}/transition",
        json={
            "actor_user_id": str(pm_tecnico_id),
            "action_id": "move",
            "target_state": "ready_for_test",
        },
    )
    assert pmt_move.status_code == 200
