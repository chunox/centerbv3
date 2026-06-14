"""Integration test: PM inbox list records."""
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from tests.record_helpers import seed_project_with_roles


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


def test_pm_lists_inbox_records_with_inbox_workbench_cap_only(
    db_session: Session, api_client: TestClient
):
    """PM con solo workbench.inbox.pm + query/report approve puede listar bandeja."""
    from app.domain.capabilities import QUERY_APPROVE, REPORT_APPROVE, WORKBENCH_INBOX_PM
    from app.models.entities import ProjectMember, ProjectRole, ProjectRoleCapability, ProjectRecord
    from datetime import date

    project, pm_id, dev_id, _qa_id = seed_project_with_roles(db_session)
    pm_role = db_session.scalars(
        __import__("sqlalchemy").select(ProjectRole).where(
            ProjectRole.project_id == project.id, ProjectRole.slug == "pm"
        )
    ).one()

    db_session.query(ProjectRoleCapability).filter(
        ProjectRoleCapability.role_id == pm_role.id
    ).delete()

    for cap in (WORKBENCH_INBOX_PM, QUERY_APPROVE, REPORT_APPROVE):
        db_session.add(
            ProjectRoleCapability(role_id=pm_role.id, capability_key=cap)
        )

    from tests.record_helpers import create_milestone_record, create_feature_record, create_query_record

    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(db_session, project, milestone, created_by=pm_id)

    report = ProjectRecord(
        project_id=project.id,
        record_type="report",
        titulo="Bug login",
        descripcion="Detalle",
        estado="pendiente",
        parent_id=feature.id,
        data={"tipo": "bug"},
        created_by=dev_id,
    )
    db_session.add(report)

    create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="Consulta SSO",
        descripcion="?",
        estado="pendiente_aprobacion_pm",
    )
    create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="Esperando PM",
        descripcion="?",
        estado="esperando_pm",
    )
    db_session.commit()

    pid = str(project.id)
    uid = str(pm_id)

    for rt in ("report", "query", "feature"):
        res = api_client.get(
            f"/api/v1/projects/{pid}/records",
            params={"record_type": rt, "actor_user_id": uid},
        )
        assert res.status_code == 200, f"{rt}: {res.text}"

    reports = api_client.get(
        f"/api/v1/projects/{pid}/records",
        params={"record_type": "report", "actor_user_id": uid},
    ).json()
    queries = api_client.get(
        f"/api/v1/projects/{pid}/records",
        params={"record_type": "query", "actor_user_id": uid},
    ).json()

    assert len(reports) == 1
    assert len(queries) == 2


def test_inbox_records_pm_queue(db_session: Session, api_client: TestClient):
    from app.models.entities import ProjectRecord, ProjectRole, ProjectRoleCapability
    from app.domain.capabilities import QUERY_APPROVE, REPORT_APPROVE, WORKBENCH_INBOX_PM
    from tests.record_helpers import (
        create_feature_record,
        create_milestone_record,
        create_query_record,
    )

    project, pm_id, dev_id, _qa_id = seed_project_with_roles(db_session)
    pm_role = db_session.scalars(
        __import__("sqlalchemy").select(ProjectRole).where(
            ProjectRole.project_id == project.id, ProjectRole.slug == "pm"
        )
    ).one()
    db_session.query(ProjectRoleCapability).filter(
        ProjectRoleCapability.role_id == pm_role.id
    ).delete()
    for cap in (WORKBENCH_INBOX_PM, QUERY_APPROVE, REPORT_APPROVE):
        db_session.add(ProjectRoleCapability(role_id=pm_role.id, capability_key=cap))

    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(db_session, project, milestone, created_by=pm_id)
    db_session.add(
        ProjectRecord(
            project_id=project.id,
            record_type="report",
            titulo="Bug",
            descripcion="x",
            estado="pendiente",
            parent_id=feature.id,
            data={"tipo": "bug"},
            created_by=dev_id,
        )
    )
    create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="PM query",
        descripcion="?",
        estado="pendiente_aprobacion_pm",
    )
    create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="Client query",
        descripcion="?",
        estado="esperando_cliente",
    )
    db_session.commit()

    pid = str(project.id)
    uid = str(pm_id)
    res = api_client.get(
        f"/api/v1/projects/{pid}/inbox-records",
        params={"queue": "pm", "actor_user_id": uid},
    )
    assert res.status_code == 200, res.text
    titles = {row["titulo"] for row in res.json()}
    assert "Bug" in titles
    assert "PM query" in titles
    assert "Client query" not in titles


def test_dev_inbox_records_only_actor_queries(db_session: Session, api_client: TestClient):
    """Dev bandeja: solo consultas creadas por el actor."""
    from tests.record_helpers import (
        create_feature_record,
        create_milestone_record,
        create_query_record,
    )

    project, pm_id, dev_id, qa_id = seed_project_with_roles(db_session)
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(db_session, project, milestone, created_by=pm_id)

    create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="Consulta dev",
        descripcion="?",
        estado="esperando_pm",
    )
    create_query_record(
        db_session,
        project,
        feature,
        created_by=qa_id,
        titulo="Consulta qa",
        descripcion="?",
        estado="esperando_pm",
    )
    db_session.commit()

    pid = str(project.id)
    res = api_client.get(
        f"/api/v1/projects/{pid}/inbox-records",
        params={"queue": "dev", "actor_user_id": str(dev_id)},
    )
    assert res.status_code == 200, res.text
    titles = {row["titulo"] for row in res.json()}
    assert titles == {"Consulta dev"}
