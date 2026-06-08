"""Tests cambio de rol de miembros (§4.3)."""

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
from app.models.entities import Project, ProjectMember, User
from app.schemas.projects import ProjectMemberUpdate
from app.services.project_members import remove_project_member, update_project_member_role
from tests.org_helpers import create_organization


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
    dev_id = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@mem.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@mem.test", password_hash="x"),
        ]
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
    session.add(
        ProjectMember(
            id=uuid4(),
            project_id=project.id,
            user_id=pm_id,
            rol="pm",
        )
    )
    member = ProjectMember(
        id=uuid4(),
        project_id=project.id,
        user_id=dev_id,
        rol="dev",
    )
    session.add(member)
    session.commit()
    return project, member, pm_id, dev_id


def test_cambiar_rol_miembro(db_session: Session):
    project, member, pm_id, _ = _seed(db_session)

    update_project_member_role(
        db_session,
        project,
        member,
        ProjectMemberUpdate(actor_user_id=pm_id, rol="qa"),
    )
    db_session.commit()

    assert member.rol == "qa"


def test_cambiar_rol_duplicado_falla(db_session: Session):
    project, member, pm_id, dev_id = _seed(db_session)
    db_session.add(
        ProjectMember(
            id=uuid4(),
            project_id=project.id,
            user_id=dev_id,
            rol="qa",
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        update_project_member_role(
            db_session,
            project,
            member,
            ProjectMemberUpdate(actor_user_id=pm_id, rol="qa"),
        )
    assert exc.value.status_code == 409


def test_patch_miembro_api(db_session: Session, api_client: TestClient):
    project, member, pm_id, _ = _seed(db_session)

    response = api_client.patch(
        f"/api/v1/projects/{project.id}/members/{member.id}",
        json={"actor_user_id": str(pm_id), "rol": "qa"},
    )
    assert response.status_code == 200
    assert response.json()["rol"] == "qa"


def test_quitar_miembro(db_session: Session):
    project, member, pm_id, dev_id = _seed(db_session)

    remove_project_member(
        db_session, project, member, actor_user_id=pm_id
    )
    db_session.commit()

    assert db_session.get(ProjectMember, member.id) is None


def test_quitar_unico_pm_falla(db_session: Session):
    project, member, pm_id, _ = _seed(db_session)
    db_session.delete(member)
    db_session.commit()
    solo_pm = db_session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.rol == "pm",
        )
    )

    with pytest.raises(HTTPException) as exc:
        remove_project_member(
            db_session, project, solo_pm, actor_user_id=pm_id
        )
    assert exc.value.status_code == 409


def test_delete_miembro_api(db_session: Session, api_client: TestClient):
    project, member, pm_id, _ = _seed(db_session)

    response = api_client.delete(
        f"/api/v1/projects/{project.id}/members/{member.id}",
        params={"actor_user_id": str(pm_id)},
    )
    assert response.status_code == 204
    assert db_session.get(ProjectMember, member.id) is None
