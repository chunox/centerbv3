"""Tests multi-tenant: organizaciones, guest projects, aislamiento."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import OrganizationInvite, OrganizationMember, Project, ProjectMember, User
from app.security import hash_password
from app.services.organizations import list_guest_projects, list_org_projects
from tests.conftest import auth_headers
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org, create_user


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


def test_list_org_projects_aislamiento(db_session: Session):
    owner_a = create_user(db_session, email="a@org.test")
    owner_b = create_user(db_session, email="b@org.test")
    org_a = create_organization(db_session, owner_id=owner_a.id, nombre="Org A")
    org_b = create_organization(db_session, owner_id=owner_b.id, nombre="Org B")
    create_project_for_org(db_session, owner_a.id, org_a, nombre="Proyecto A")
    create_project_for_org(db_session, owner_b.id, org_b, nombre="Proyecto B")
    db_session.commit()

    projects_a = list_org_projects(db_session, org_a.id, owner_a.id)
    assert len(projects_a) == 1
    assert projects_a[0].nombre == "Proyecto A"

    with pytest.raises(HTTPException) as exc:
        list_org_projects(db_session, org_b.id, owner_a.id)
    assert exc.value.status_code == 403


def test_guest_project_sin_org_membership(db_session: Session):
    pm_id = uuid4()
    cliente_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@guest.test", password_hash="x"),
            User(
                id=cliente_id,
                nombre="Cliente",
                email="cli@guest.test",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(
        db_session, pm_id, org, template_slug="t1_cliente_clasico"
    )
    add_member_with_slug(db_session, project, cliente_id, 'cliente')
    db_session.commit()

    guests = list_guest_projects(db_session, cliente_id)
    assert len(guests) == 1
    assert guests[0].id == project.id

    org_projects = list_org_projects(db_session, org.id, pm_id)
    assert len(org_projects) == 1


def test_auth_register_y_crear_org(api_client: TestClient, db_session: Session):
    reg = api_client.post(
        "/api/v1/auth/register",
        json={
            "nombre": "Nuevo",
            "email": "nuevo@test.com",
            "password": "demo12345",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]

    org_resp = api_client.post(
        "/api/v1/organizations",
        json={"nombre": "Mi Empresa"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert org_resp.status_code == 201
    org_id = UUID(org_resp.json()["id"])

    user = db_session.scalar(select(User).where(User.email == "nuevo@test.com"))
    assert user is not None
    member = db_session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
        )
    )
    assert member is not None
    assert member.rol == "owner"


def test_create_project_requiere_org_admin(api_client: TestClient, db_session: Session):
    owner_id = uuid4()
    outsider_id = uuid4()
    db_session.add_all(
        [
            User(id=owner_id, nombre="Owner", email="own@test.com", password_hash="x"),
            User(
                id=outsider_id,
                nombre="Out",
                email="out@test.com",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(db_session, owner_id=owner_id)
    db_session.commit()

    resp = api_client.post(
        "/api/v1/projects",
        json={
            "organization_id": str(org.id),
            "nombre": "Nuevo",
            "tipo": "interno",
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
        },
        headers=auth_headers(outsider_id),
    )
    assert resp.status_code == 403


def test_list_and_revoke_org_invites(api_client: TestClient, db_session: Session):
    reg = api_client.post(
        "/api/v1/auth/register",
        json={
            "nombre": "Admin",
            "email": "admin-inv@test.com",
            "password": "demo12345",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]

    org_resp = api_client.post(
        "/api/v1/organizations",
        json={"nombre": "Invite Org"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert org_resp.status_code == 201
    org_id = org_resp.json()["id"]

    create_resp = api_client.post(
        f"/api/v1/organizations/{org_id}/invites",
        json={"email": "invitee@test.com", "rol": "member"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    invite_id = create_resp.json()["id"]

    list_resp = api_client.get(
        f"/api/v1/organizations/{org_id}/invites",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["email"] == "invitee@test.com"

    delete_resp = api_client.delete(
        f"/api/v1/organizations/{org_id}/invites/{invite_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_resp.status_code == 204
    assert db_session.get(OrganizationInvite, UUID(invite_id)) is None

    list_after = api_client.get(
        f"/api/v1/organizations/{org_id}/invites",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_after.status_code == 200
    assert list_after.json() == []


def test_list_projects_guest_api(api_client: TestClient, db_session: Session):
    pm_id = uuid4()
    cliente_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm2@guest.test", password_hash="x"),
            User(
                id=cliente_id,
                nombre="Cli",
                email="cli2@guest.test",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(
        db_session, pm_id, org, template_slug="t1_cliente_clasico"
    )
    add_member_with_slug(db_session, project, cliente_id, 'cliente')
    db_session.commit()

    resp = api_client.get(
        "/api/v1/projects",
        params={"guest": "true"},
        headers=auth_headers(cliente_id),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == str(project.id)
