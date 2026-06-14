"""Tests for create_record side effect and communication rules."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import ProjectRecord, User
from tests.org_helpers import create_organization, create_project_for_org
from tests.record_helpers import create_feature_record, create_milestone_record, seed_project_with_roles


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


def test_create_record_side_effect_on_feature(db_session: Session):
    pm_id = uuid4()
    db_session.add(User(id=pm_id, nombre="PM", email="pm@cr.test", password_hash="x"))
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org, nombre="P")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(db_session, project, milestone, created_by=pm_id)
    db_session.commit()

    from app.services.workflow.side_effects import run_side_effect

    run_side_effect(
        db_session,
        project=project,
        entity=feature,
        entity_type="feature",
        action_id="test",
        actor_user_id=pm_id,
        effect={
            "type": "create_record",
            "target": {
                "record_type": "task",
                "parent": "entity",
                "titulo": "Tarea auto",
                "initial_state": "backlog",
            },
        },
        form_data=None,
        side_effect_context=None,
        entidad_tipo="feature",
    )
    db_session.flush()
    tasks = db_session.query(ProjectRecord).filter(
        ProjectRecord.parent_id == feature.id,
        ProjectRecord.record_type == "task",
    ).all()
    assert any(t.titulo == "Tarea auto" for t in tasks)


def test_communication_rules_api(db_session: Session, api_client: TestClient):
    project, pm_id, _, _ = seed_project_with_roles(db_session)
    pid = str(project.id)
    uid = str(pm_id)

    res = api_client.get(f"/api/v1/projects/{pid}/communication-rules?user_id={uid}")
    assert res.status_code == 200
    assert len(res.json()["rules"]) >= 1

    rules = res.json()["rules"]
    rules[0]["enabled"] = False
    put = api_client.put(
        f"/api/v1/projects/{pid}/communication-rules",
        json={"actor_user_id": uid, "rules": rules},
    )
    assert put.status_code == 200
    assert put.json()["rules"][0]["enabled"] is False
