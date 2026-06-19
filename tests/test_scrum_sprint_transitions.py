"""Tests comprometer/devolver sprint v2: reparent story, filtros list_records."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Project, User
from app.services.packs import seed_project_from_pack
from app.services.records.generic_store import list_records, transition_record
from app.services.scrum_effort import get_scrum_item_sprint_id
from app.services.scrum_tasks import create_epic_task, create_story_task
from app.services.scrum_v2_structure import get_product_backlog_milestone
from tests.org_helpers import add_member_with_slug, create_organization
from tests.record_helpers import create_sprint_record


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


def _seed_scrum_project(session: Session):
    pm_id = uuid4()
    org = create_organization(session, owner_id=pm_id)
    session.add(
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
        nombre="Scrum Test",
        estado="activo",
        created_by=pm_id,
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    session.add(project)
    session.flush()
    seed_project_from_pack(session, project, "software", template_slug="t6_scrum_interno")
    add_member_with_slug(session, project, pm_id, "pm")
    session.commit()
    return project, pm_id


def test_comprometer_y_volver_reparent_story(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    backlog = get_product_backlog_milestone(db_session, project.id)

    epic = create_epic_task(db_session, project, titulo="Plataforma", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint 1",
        orden=1,
    )
    db_session.commit()

    assert story.parent_id == backlog.id

    transition_record(
        db_session,
        project,
        story,
        action_id="comprometer_sprint",
        actor_user_id=pm_id,
        side_effect_context={"sprint_id": str(sprint.id)},
    )
    db_session.commit()
    db_session.refresh(story)

    assert story.parent_id == sprint.id
    assert get_scrum_item_sprint_id(db_session, story) == sprint.id
    assert story.estado == "pendiente"
    assert story.fecha_inicio == date(2026, 3, 1)

    transition_record(
        db_session,
        project,
        story,
        action_id="volver_al_backlog",
        actor_user_id=pm_id,
    )
    db_session.commit()
    db_session.refresh(story)

    assert story.parent_id == backlog.id
    assert get_scrum_item_sprint_id(db_session, story) is None
    assert story.estado == "product_backlog"


def test_list_records_sprint_id_filter(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    backlog = get_product_backlog_milestone(db_session, project.id)
    sprint_a = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    sprint_b = create_sprint_record(db_session, project, created_by=pm_id, nombre="S2", orden=2)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)

    story_a = create_story_task(
        db_session,
        project,
        titulo="En S1",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story_a.parent_id = sprint_a.id
    story_b = create_story_task(
        db_session,
        project,
        titulo="En S2",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story_b.parent_id = sprint_b.id
    db_session.commit()

    rows = list_records(
        db_session,
        project.id,
        record_type="task",
        sprint_id=sprint_a.id,
    )
    story_rows = [r for r in rows if r.data.get("scrum_role") == "story"]
    assert len(story_rows) == 1
    assert story_rows[0].id == story_a.id
    assert backlog is not None


def test_list_records_in_product_backlog_filter(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    sprint = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)

    in_backlog = create_story_task(
        db_session,
        project,
        titulo="Backlog",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    committed = create_story_task(
        db_session,
        project,
        titulo="Committed",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    committed.parent_id = sprint.id
    committed.estado = "en_progreso"
    wrong_state = create_story_task(
        db_session,
        project,
        titulo="Sin sprint pero en progreso",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    wrong_state.estado = "en_progreso"
    db_session.commit()

    rows = list_records(
        db_session,
        project.id,
        record_type="task",
        in_product_backlog=True,
    )
    ids = {r.id for r in rows}
    assert in_backlog.id in ids
    assert wrong_state.id in ids
    assert committed.id not in ids
