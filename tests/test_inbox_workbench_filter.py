"""Inbox records filtered by workbench queue_filter."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from tests.record_helpers import (
    create_feature_record,
    create_milestone_record,
    create_query_record,
    seed_project_with_roles,
)


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


def test_inbox_records_by_workbench_key(db_session: Session, api_client: TestClient):
    project, pm_id, dev_id, _ = seed_project_with_roles(db_session)
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(db_session, project, milestone, created_by=pm_id)
    create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="Mi consulta",
        descripcion="?",
        estado="esperando_pm",
    )
    create_query_record(
        db_session,
        project,
        feature,
        created_by=pm_id,
        titulo="Consulta ajena",
        descripcion="?",
        estado="esperando_pm",
    )
    db_session.commit()

    pid = str(project.id)
    res = api_client.get(
        f"/api/v1/projects/{pid}/inbox-records",
        params={
            "workbench_key": "inbox_dev",
            "actor_user_id": str(dev_id),
        },
    )
    assert res.status_code == 200, res.text
    titles = {row["titulo"] for row in res.json()}
    assert titles == {"Mi consulta"}
