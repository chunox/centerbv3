"""Scrum v2: workflow de historias expuesto como story (no feature phantom)."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Project, ProjectRecordType, User
from app.services.packs import seed_project_from_pack
from app.services.records.registry import registry
from app.services.workflow.store import workflow_entity_types
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


def test_scrum_project_seeds_dev_task_workflow(db_session: Session):
    from app.services.workflow.store import get_active_workflow
    from app.domain.workflow_templates import default_task_workflow_scrum_dev

    pm_id = uuid4()
    org = create_organization(db_session, owner_id=pm_id)
    db_session.add(
        User(
            id=pm_id,
            email="pm@test.local",
            nombre="PM",
            password_hash="x",
        )
    )
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        nombre="Scrum WF",
        estado="activo",
        created_by=pm_id,
        template_slug="t6_scrum_interno",
        pack_slug="software-scrum",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    db_session.add(project)
    db_session.flush()
    seed_project_from_pack(db_session, project, "software-scrum", template_slug="t6_scrum_interno")
    db_session.commit()

    task_wf = get_active_workflow(db_session, project.id, "task")
    assert task_wf is not None
    assert task_wf["initial_state"] == default_task_workflow_scrum_dev()["initial_state"]
    assert "move" in {t["id"] for t in task_wf.get("transitions", [])}


def test_scrum_project_exposes_story_workflow_not_feature(db_session: Session):
    pm_id = uuid4()
    org = create_organization(db_session, owner_id=pm_id)
    db_session.add(
        User(
            id=pm_id,
            email="pm@test.local",
            nombre="PM",
            password_hash="x",
        )
    )
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        nombre="Scrum WF",
        estado="activo",
        created_by=pm_id,
        template_slug="t6_scrum_interno",
        pack_slug="software-scrum",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    db_session.add(project)
    db_session.flush()
    seed_project_from_pack(db_session, project, "software-scrum", template_slug="t6_scrum_interno")
    db_session.commit()

    types = registry.workflow_entity_types_for_project(db_session, project.id)
    record_types = list(
        db_session.scalars(
            select(ProjectRecordType.key).where(
                ProjectRecordType.project_id == project.id
            )
        )
    )
    assert "feature" not in record_types
    assert "feature" not in types
    assert "task" in types
    assert "sprint" in types or "product_backlog" in types
    assert "feature" not in workflow_entity_types(db_session, project.id)
