"""Tests cierre de sprint con carry-over opcional."""
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Project, User
from app.services.packs import seed_project_from_pack
from app.services.scrum_sprint_close import close_scrum_sprint, resolve_next_open_sprint
from app.services.scrum_tasks import create_dev_task, create_epic_task, create_story_task
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
    estado: str,
    epic=None,
):
    if epic is None:
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


def test_close_without_carry_over_keeps_incomplete_in_closed_sprint(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    s1 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    s2 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S2", orden=2)
    incomplete = _story_in_sprint(
        db_session, project, pm_id, s1, titulo="In progress", estado="en_progreso"
    )
    db_session.commit()

    result = close_scrum_sprint(
        db_session, project, s1, pm_id, carry_over_to_next_sprint=False
    )
    db_session.commit()
    db_session.refresh(s1)
    db_session.refresh(incomplete)

    assert result.target_sprint_id is None
    assert result.carried_over_story_ids == []
    assert s1.estado == "completado"
    assert incomplete.parent_id == s1.id
    assert incomplete.estado == "en_progreso"


def test_close_with_carry_over_moves_incomplete_to_next_sprint(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    s1 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    s2 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S2", orden=2)
    completed = _story_in_sprint(
        db_session, project, pm_id, s1, titulo="Done", estado="completado"
    )
    incomplete = _story_in_sprint(
        db_session, project, pm_id, s1, titulo="WIP", estado="en_progreso"
    )
    db_session.commit()

    result = close_scrum_sprint(
        db_session, project, s1, pm_id, carry_over_to_next_sprint=True
    )
    db_session.commit()
    db_session.refresh(s1)
    db_session.refresh(completed)
    db_session.refresh(incomplete)

    assert result.target_sprint_id == s2.id
    assert result.carried_over_story_ids == [incomplete.id]
    assert s1.estado == "completado"
    assert completed.parent_id == s1.id
    assert incomplete.parent_id == s2.id
    assert incomplete.estado == "en_progreso"


def test_close_carry_over_moves_dev_tasks(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    s1 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    s2 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S2", orden=2)
    story = _story_in_sprint(
        db_session, project, pm_id, s1, titulo="WIP", estado="en_progreso"
    )
    dev = create_dev_task(
        db_session,
        project,
        titulo="Dev task",
        created_by=pm_id,
        story_id=story.id,
    )
    db_session.commit()

    close_scrum_sprint(db_session, project, s1, pm_id, carry_over_to_next_sprint=True)
    db_session.commit()
    db_session.refresh(dev)

    assert dev.parent_id == s2.id


def test_close_carry_over_without_next_sprint_raises(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    s1 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    _story_in_sprint(
        db_session, project, pm_id, s1, titulo="WIP", estado="en_progreso"
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        close_scrum_sprint(db_session, project, s1, pm_id, carry_over_to_next_sprint=True)
    assert exc.value.status_code == 400


def test_close_already_completed_sprint_raises(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    s1 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    s1.estado = "completado"
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        close_scrum_sprint(db_session, project, s1, pm_id, carry_over_to_next_sprint=False)
    assert exc.value.status_code == 409


def test_resolve_next_open_sprint_skips_closed(db_session: Session):
    project, pm_id = _seed_scrum_project(db_session)
    s1 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S1", orden=1)
    s2 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S2", orden=2)
    s2.estado = "completado"
    s3 = create_sprint_record(db_session, project, created_by=pm_id, nombre="S3", orden=3)
    db_session.commit()

    nxt = resolve_next_open_sprint(db_session, project.id, s1.id)
    assert nxt is not None
    assert nxt.id == s3.id
