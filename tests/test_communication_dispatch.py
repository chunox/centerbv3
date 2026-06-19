"""Tests for communication dispatch integration."""
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
from tests.conftest import auth_headers
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


def test_dispatch_record_created_report(db_session: Session):
    from app.services.communication.engine import (
        CommunicationContext,
        simulate_communication_rules,
    )

    project, pm_id, _, _ = seed_project_with_roles(db_session)
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(db_session, project, milestone, created_by=pm_id)
    report = ProjectRecord(
        project_id=project.id,
        record_type="report",
        parent_id=feature.id,
        titulo="Bug",
        estado="pendiente",
        data={"reported_by": str(pm_id), "tipo": "bug"},
        created_by=pm_id,
    )
    db_session.add(report)
    db_session.flush()

    ctx = CommunicationContext(
        event="on_record_created",
        project=project,
        author_id=pm_id,
        entity_type="report",
        record_type="report",
        entity_id=report.id,
        record=report,
    )
    matched = simulate_communication_rules(db_session, ctx)
    assert any(m.rule_id == "report_created_pm" for m in matched)


def test_simulate_communication_rules(api_client: TestClient, db_session: Session):
    project, pm_id, _, _ = seed_project_with_roles(db_session)
    db_session.commit()
    res = api_client.post(
        f"/api/v1/projects/{project.id}/communication-rules/simulate",
        json={
            "event": "on_record_created",
            "record_type": "report",
            "sandbox": True,
        },
        headers=auth_headers(pm_id),
    )
    assert res.status_code == 200
    assert "matched" in res.json()


def test_inbox_summary_counts_by_workbench(db_session: Session):
    from app.services.inbox_summary import build_inbox_summary

    project, pm_id, _, _ = seed_project_with_roles(db_session)
    summary = build_inbox_summary(db_session, project, viewer_user_id=pm_id)
    assert summary.counts_by_workbench is not None
    assert "inbox_pm" in summary.counts_by_workbench
