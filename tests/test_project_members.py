"""Tests cambio de rol de miembros (§4.3)."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ProjectMember, ProjectRole, User
from app.schemas.projects import ProjectMemberUpdate
from app.services.project_members import remove_project_member, update_project_member_role
from tests.conftest import auth_headers
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org


def _role_id(session: Session, project_id, slug: str):
    return session.scalar(
        select(ProjectRole.id).where(
            ProjectRole.project_id == project_id, ProjectRole.slug == slug
        )
    )


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
    project = create_project_for_org(session, pm_id, org=org)
    member = add_member_with_slug(session, project, dev_id, "dev")
    session.commit()
    return project, member, pm_id, dev_id


def test_cambiar_rol_miembro(db_session: Session):
    project, member, pm_id, _ = _seed(db_session)
    qa_role_id = _role_id(db_session, project.id, "qa")

    update_project_member_role(
        db_session,
        project,
        member,
        ProjectMemberUpdate(role_id=qa_role_id),
        actor_user_id=pm_id,
    )
    db_session.commit()

    role = db_session.get(ProjectRole, member.role_id)
    assert role is not None
    assert role.slug == "qa"


def test_cambiar_rol_duplicado_falla(db_session: Session):
    project, member, pm_id, dev_id = _seed(db_session)
    qa_role_id = _role_id(db_session, project.id, "qa")
    add_member_with_slug(db_session, project, dev_id, "qa")
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        update_project_member_role(
            db_session,
            project,
            member,
            ProjectMemberUpdate(role_id=qa_role_id),
            actor_user_id=pm_id,
        )
    assert exc.value.status_code == 409


def test_patch_miembro_api(db_session: Session, api_client: TestClient):
    project, member, pm_id, _ = _seed(db_session)
    qa_role_id = _role_id(db_session, project.id, "qa")

    response = api_client.patch(
        f"/api/v1/projects/{project.id}/members/{member.id}",
        json={"role_id": str(qa_role_id)},
        headers=auth_headers(pm_id),
    )
    assert response.status_code == 200
    assert response.json()["role_slug"] == "qa"


def test_quitar_miembro(db_session: Session):
    project, member, pm_id, _ = _seed(db_session)
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
        select(ProjectMember)
        .join(ProjectRole, ProjectRole.id == ProjectMember.role_id)
        .where(
            ProjectMember.project_id == project.id,
            ProjectRole.slug == "pm",
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
        headers=auth_headers(pm_id),
    )
    assert response.status_code == 204
