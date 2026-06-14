"""Tests cerrar/reabrir/cancelar proyecto (§4.2)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Project, ProjectMember, User
from app.services.projects import apply_project_estado_action
from tests.org_helpers import add_member_with_slug, create_organization


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed(session: Session):
    pm_id = uuid4()
    session.add(
        User(id=pm_id, nombre="PM", email="pm@est.test", password_hash="x")
    )
    org = create_organization(session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="P",
        profile_slug="internal",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    add_member_with_slug(session, project, pm_id, 'pm')
    session.commit()
    return project, pm_id


def test_cerrar_y_reabrir_proyecto(db_session: Session):
    project, pm_id = _seed(db_session)
    apply_project_estado_action(
        db_session, project, action="cerrar", actor_user_id=pm_id
    )
    assert project.estado == "cerrado"

    apply_project_estado_action(
        db_session, project, action="reabrir", actor_user_id=pm_id
    )
    assert project.estado == "activo"


def test_cancelar_es_terminal(db_session: Session):
    project, pm_id = _seed(db_session)
    apply_project_estado_action(
        db_session, project, action="cancelar", actor_user_id=pm_id
    )
    assert project.estado == "cancelado"

    with pytest.raises(HTTPException) as exc:
        apply_project_estado_action(
            db_session, project, action="reabrir", actor_user_id=pm_id
        )
    assert exc.value.status_code == 409
