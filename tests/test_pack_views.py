"""Tests de workbenches con custom_view_key en access-context."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.packs import ensure_system_packs
from app.services.workflow.store import get_workbenches
from tests.org_helpers import create_organization, create_project_for_org, create_user


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
        ensure_system_packs(session)
        session.commit()
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


def _workbench_custom_keys(access: dict) -> dict[str, str | None]:
    return {wb["key"]: wb.get("custom_view_key") for wb in access.get("workbenches", [])}


@pytest.mark.parametrize(
    "pack_slug,expected_keys",
    [
        (
            "creativo",
            {
                "overview": "creativo.overview",
                "scope": "creativo.scope",
                "board": "creativo.board",
                "inbox_revision": "creativo.inbox_revision",
                "inbox_cliente": "creativo.inbox_cliente",
            },
        ),
        (
            "software",
            {
                "overview": "software.overview",
                "inbox_pm": "software.inbox_pm",
                "inbox_dev": "software.inbox_dev",
                "inbox_qa": "software.inbox_qa",
                "kanban": "software.kanban",
                "uat": "software.uat",
                "scope": "software.scope",
            },
        ),
        (
            "marketing360",
            {
                "overview": "marketing360.overview",
                "scope": "marketing360.scope",
                "board": "marketing360.board",
                "mi_produccion": "marketing360.mi_produccion",
                "calendario": "marketing360.calendario",
                "gantt": "marketing360.gantt",
                "aprobaciones": "marketing360.aprobaciones",
            },
        ),
    ],
)
def test_pack_workbenches_expose_custom_view_key(
    api_client: TestClient,
    db_session: Session,
    pack_slug: str,
    expected_keys: dict[str, str],
):
    owner = create_user(db_session, nombre="Owner")
    org = create_organization(db_session, nombre="Org pack views", owner_id=owner.id)
    project = create_project_for_org(
        db_session,
        owner.id,
        org,
        nombre=f"Pack views {pack_slug}",
        pack_slug=pack_slug,
    )
    db_session.commit()

    workbenches = get_workbenches(db_session, project.id)
    keys = {wb["key"]: wb.get("custom_view_key") for wb in workbenches}

    for wb_key, custom_key in expected_keys.items():
        assert keys.get(wb_key) == custom_key, (
            f"{pack_slug}/{wb_key} expected {custom_key}, got {keys.get(wb_key)}"
        )

    for wb in workbenches:
        if wb.get("custom_view_key"):
            assert wb.get("view_type") == "custom"
