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
from app.models.entities import Feature, Milestone, Project, ProjectMember, ProjectRole, Task, User
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
    "template_slug,expected_roles,expected_tipo,expected_creator",
    [
        (
            "t1_cliente_clasico",
            {"pm", "tech_lead", "dev", "qa", "cliente"},
            "con_cliente",
            "pm",
        ),
        (
            "t2_cliente_pm_tecnico",
            {"pm_tecnico", "dev", "qa", "cliente"},
            "con_cliente",
            "pm_tecnico",
        ),
        (
            "t3_interno_clasico",
            {"pm", "tech_lead", "dev", "qa"},
            "interno",
            "pm",
        ),
        (
            "t4_interno_pm_tecnico",
            {"pm_tecnico", "dev", "qa"},
            "interno",
            "pm_tecnico",
        ),
        (
            "t5_freestyle",
            {"pm", "pm_tecnico", "dev", "tech_lead", "qa", "cliente"},
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
        f"/api/v1/projects/{project_id}/milestones",
        json={
            "nombre": "Hito TL",
            "tipo": "entrega",
            "orden": 1,
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-06-30",
            "created_by": str(tl.id),
        },
    )
    assert response.status_code == 201


def test_pm_blocked_on_task_move_pm_tecnico_allowed(
    db_session: Session, api_client: TestClient
):
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
        nombre="F1",
        tipo="desarrollo",
        prioridad="media",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        estado="pendiente",
        created_by=pm_id,
    )
    db_session.add(feature)
    task = Task(
        id=uuid4(),
        feature_id=feature.id,
        project_id=project.id,
        titulo="T1",
        estado="backlog",
        created_by=pm_tecnico_id,
    )
    db_session.add(task)
    db_session.commit()

    pm_move = api_client.patch(
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}"
        f"/features/{feature.id}/tasks/{task.id}/move",
        json={"actor_user_id": str(pm_id), "estado": "in_progress"},
    )
    assert pm_move.status_code == 403

    pmt_move = api_client.patch(
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}"
        f"/features/{feature.id}/tasks/{task.id}/move",
        json={"actor_user_id": str(pm_tecnico_id), "estado": "in_progress"},
    )
    assert pmt_move.status_code == 200
