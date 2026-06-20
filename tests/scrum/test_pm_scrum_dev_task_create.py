"""PM puede crear dev tasks Scrum vía API genérica."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.domain.capabilities import KANBAN_TASK_CREATE, LEGACY_ROLE_CAPABILITIES
from app.models.entities import Project, User
from app.services.delivery.scrum import ScrumRecordService
from app.services.packs import seed_project_from_pack
from app.services.scrum_tasks import create_epic_task, create_story_task
from app.services.workflow.authorize import assert_capability
from app.schemas.records import RecordCreate
from tests.org_helpers import add_member_with_slug, create_organization


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


def test_pm_legacy_caps_include_kanban_task_create():
    assert KANBAN_TASK_CREATE in LEGACY_ROLE_CAPABILITIES["pm"]


def test_pm_can_assert_kanban_task_create_after_scrum_seed(db_session: Session):
    pm_id = uuid4()
    org = create_organization(db_session, owner_id=pm_id)
    db_session.add(
        User(id=pm_id, email="pm@test.local", nombre="PM", password_hash="x")
    )
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        nombre="Scrum",
        estado="activo",
        created_by=pm_id,
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    db_session.add(project)
    db_session.flush()
    seed_project_from_pack(db_session, project, "software", template_slug="t6_scrum_interno")
    add_member_with_slug(db_session, project, pm_id, "pm")
    db_session.commit()

    assert_capability(db_session, project.id, pm_id, KANBAN_TASK_CREATE)

    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    db_session.commit()

    service = ScrumRecordService()
    payload = RecordCreate(
        record_type="task",
        titulo="Dev task",
        data={"scrum_role": "dev", "parent_task_id": str(story.id)},
    )
    service.assert_task_create(db_session, project, payload, pm_id)


def test_pm_can_complete_scrum_dev_task_via_completar(db_session: Session):
    from app.domain.records.types import RecordRef
    from app.services.scrum_tasks import create_dev_task
    from app.services.workflow.engine import apply_record_transition

    pm_id = uuid4()
    org = create_organization(db_session, owner_id=pm_id)
    db_session.add(
        User(id=pm_id, email="pm-complete@test.local", nombre="PM", password_hash="x")
    )
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        nombre="Scrum",
        estado="activo",
        created_by=pm_id,
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    db_session.add(project)
    db_session.flush()
    seed_project_from_pack(db_session, project, "software", template_slug="t6_scrum_interno")
    add_member_with_slug(db_session, project, pm_id, "pm")

    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    dev_task = create_dev_task(
        db_session,
        project,
        titulo="Dev task",
        created_by=pm_id,
        story_id=story.id,
        initial_state="in_progress",
    )
    db_session.commit()

    apply_record_transition(
        db_session,
        project,
        dev_task,
        record_ref=RecordRef(
            id=dev_task.id,
            record_type=dev_task.record_type,
            project_id=project.id,
        ),
        action_id="completar",
        actor_user_id=pm_id,
    )
    db_session.refresh(dev_task)
    assert dev_task.estado == "completed"
