"""Tests cancelación de sprint: eliminar vacío, cancelar historias o devolver al backlog."""
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Project, ProjectRecord, User
from app.services.packs import seed_project_from_pack
from app.services.scrum_sprint_cancel import cancel_scrum_sprint
from app.services.scrum_tasks import create_epic_task, create_story_task
from app.services.scrum_v2_structure import list_stories_for_sprint
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


def _story_in_sprint(
    session: Session,
    project: Project,
    pm_id,
    sprint,
    *,
    titulo: str,
    estado: str = "pendiente",
):
    epic = create_epic_task(session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        session,
        project,
        titulo=titulo,
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story.parent_id = sprint.id
    story.estado = estado
    session.flush()
    return story


def test_cancel_empty_sprint_deletes_record(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    sprint = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    sprint_id = sprint.id
    db_session.commit()

    result = cancel_scrum_sprint(db_session, project, sprint, pm_id)
    db_session.commit()

    assert result.deleted is True
    assert result.estado is None
    assert db_session.get(ProjectRecord, sprint_id) is None


def test_cancel_sprint_cancels_stories_by_default(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    sprint = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    story = _story_in_sprint(db_session, project, pm_id, sprint, titulo="Historia")
    db_session.commit()

    result = cancel_scrum_sprint(db_session, project, sprint, pm_id)
    db_session.commit()
    db_session.refresh(sprint)
    db_session.refresh(story)

    assert result.deleted is False
    assert result.estado == "cancelado"
    assert sprint.estado == "cancelado"
    assert story.estado == "cancel"
    assert result.cancelled_story_ids == [story.id]


def test_cancel_sprint_return_stories_to_backlog_deletes_sprint(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    sprint = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    story = _story_in_sprint(db_session, project, pm_id, sprint, titulo="Historia")
    sprint_id = sprint.id
    db_session.commit()

    result = cancel_scrum_sprint(
        db_session,
        project,
        sprint,
        pm_id,
        return_stories_to_backlog=True,
    )
    db_session.commit()
    db_session.refresh(story)

    assert result.deleted is True
    assert db_session.get(ProjectRecord, sprint_id) is None
    assert story.estado == "product_backlog"
    assert story.parent_id is not None
    assert list_stories_for_sprint(db_session, project.id, sprint_id) == []
    assert result.returned_story_ids == [story.id]


def test_cancel_unassign_en_progreso_story_can_recommit(db_session: Session):
    from app.services.records.generic_store import transition_record

    project, pm_id = _seed_scrum_project(db_session)
    s1 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    s2 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S2", orden=2)
    story = _story_in_sprint(
        db_session,
        project,
        pm_id,
        s1,
        titulo="WIP",
        estado="en_progreso",
    )
    db_session.commit()

    cancel_scrum_sprint(
        db_session,
        project,
        s1,
        pm_id,
        return_stories_to_backlog=True,
    )
    db_session.commit()
    db_session.refresh(story)

    assert story.estado == "product_backlog"

    transition_record(
        db_session,
        project,
        story,
        action_id="comprometer_sprint",
        actor_user_id=pm_id,
        side_effect_context={"sprint_id": str(s2.id)},
    )
    db_session.commit()
    db_session.refresh(story)

    assert story.estado == "pendiente"
    assert story.parent_id == s2.id


def test_cancel_already_terminal_sprint_raises(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    sprint = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    sprint.estado = "cancelado"
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        cancel_scrum_sprint(db_session, project, sprint, pm_id)
    assert exc.value.status_code == 409
