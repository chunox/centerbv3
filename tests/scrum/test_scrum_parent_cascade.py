"""Tests cascade manual padre→hijos Scrum."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Project, User
from app.services.packs import seed_project_from_pack
from app.services.records.generic_store import transition_record
from app.services.scrum_parent_cascade import (
    apply_scrum_parent_cascade,
    build_cascade_preview,
    count_incomplete_scrum_children,
)
from app.services.scrum_tasks import create_dev_task, create_epic_task, create_story_task
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


def _seed(db: Session):
    pm_id = uuid4()
    org = create_organization(db, owner_id=pm_id)
    db.add(User(id=pm_id, email="pm@test.local", nombre="PM", password_hash="x"))
    project = Project(
        id=uuid4(),
        organization_id=org.id,
        nombre="Cascade Test",
        estado="activo",
        created_by=pm_id,
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    db.add(project)
    db.flush()
    seed_project_from_pack(db, project, "software", template_slug="t6_scrum_interno")
    add_member_with_slug(db, project, pm_id, "pm")
    db.commit()
    return project, pm_id


def test_cascade_preview_counts_open_dev_tasks(db_session: Session):
    project, pm_id = _seed(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session, project, titulo="Story", created_by=pm_id, epic_task_id=epic.id
    )
    create_dev_task(db_session, project, titulo="Dev", created_by=pm_id, story_id=story.id)
    db_session.commit()

    preview = build_cascade_preview(db_session, project, story, target_state="completado")
    assert preview["incomplete_count"] == 1
    assert preview["requires_confirmation"] is True

    count, _ = count_incomplete_scrum_children(
        db_session, project, story, target_state="completado"
    )
    assert count == 1


def test_story_completar_cascades_via_after_transition(db_session: Session):
    project, pm_id = _seed(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session, project, titulo="Story", created_by=pm_id, epic_task_id=epic.id
    )
    sprint = create_sprint_record(
        db_session, project, created_by=pm_id, nombre="S1", orden=1
    )
    create_dev_task(
        db_session,
        project,
        titulo="Dev",
        created_by=pm_id,
        story_id=story.id,
        initial_state="to_do",
    )
    db_session.commit()

    transition_record(
        db_session,
        project,
        story,
        action_id="comprometer_sprint",
        actor_user_id=pm_id,
        side_effect_context={"sprint_id": str(sprint.id)},
    )
    story.estado = "en_progreso"
    db_session.flush()

    from app.services.scrum_v2_structure import list_all_dev_tasks_for_story

    dev = list_all_dev_tasks_for_story(db_session, project.id, story.id)[0]
    transition_record(
        db_session,
        project,
        story,
        action_id="completar",
        actor_user_id=pm_id,
    )
    db_session.commit()
    db_session.refresh(dev)

    assert dev.estado == "completed"


def test_cascade_preview_detects_backlog_stories(db_session: Session):
    project, pm_id = _seed(db_session)
    backlog = get_product_backlog_milestone(db_session, project.id)
    sprint = create_sprint_record(
        db_session, project, created_by=pm_id, nombre="S1", orden=1
    )
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    backlog_story = create_story_task(
        db_session,
        project,
        titulo="Backlog Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    backlog_story.parent_id = backlog.id
    backlog_story.estado = "product_backlog"
    sprint_story = create_story_task(
        db_session,
        project,
        titulo="Sprint Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint_story.parent_id = sprint.id
    sprint_story.estado = "en_progreso"
    create_dev_task(
        db_session,
        project,
        titulo="Dev open",
        created_by=pm_id,
        story_id=sprint_story.id,
        initial_state="to_do",
    )
    db_session.commit()

    preview = build_cascade_preview(db_session, project, epic, target_state="cerrada")
    assert preview["has_backlog_children"] is True
    assert preview["has_sprint_children"] is True
    assert preview["backlog_incomplete_count"] == 1
    assert preview["sprint_incomplete_count"] >= 1
    assert preview["incomplete_count"] >= 2
    assert any("Backlog Story" in label for label in preview["backlog_child_labels"])
    assert any("Sprint Story" in label for label in preview["sprint_child_labels"])


def test_cancel_backlog_then_sprint_mode(db_session: Session):
    project, pm_id = _seed(db_session)
    backlog = get_product_backlog_milestone(db_session, project.id)
    sprint = create_sprint_record(
        db_session, project, created_by=pm_id, nombre="S1", orden=1
    )
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    backlog_story = create_story_task(
        db_session,
        project,
        titulo="Backlog Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    backlog_story.parent_id = backlog.id
    backlog_story.estado = "product_backlog"
    create_dev_task(
        db_session,
        project,
        titulo="Backlog Dev",
        created_by=pm_id,
        story_id=backlog_story.id,
        initial_state="to_do",
    )
    sprint_story = create_story_task(
        db_session,
        project,
        titulo="Sprint Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint_story.parent_id = sprint.id
    sprint_story.estado = "en_progreso"
    dev = create_dev_task(
        db_session,
        project,
        titulo="Sprint Dev",
        created_by=pm_id,
        story_id=sprint_story.id,
        initial_state="to_do",
    )
    epic.estado = "cerrada"
    db_session.flush()

    apply_scrum_parent_cascade(
        db_session,
        project,
        epic,
        target_state="cerrada",
        actor_user_id=pm_id,
        mode="cancel_backlog_then_sprint",
    )
    db_session.commit()
    db_session.refresh(backlog_story)
    db_session.refresh(dev)

    assert backlog_story.estado == "cancelado"
    assert dev.estado == "completed"


def test_cascade_backlog_only_mode(db_session: Session):
    project, pm_id = _seed(db_session)
    backlog = get_product_backlog_milestone(db_session, project.id)
    sprint = create_sprint_record(
        db_session, project, created_by=pm_id, nombre="S1", orden=1
    )
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    backlog_story = create_story_task(
        db_session,
        project,
        titulo="Backlog Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    backlog_story.parent_id = backlog.id
    backlog_story.estado = "product_backlog"
    backlog_dev = create_dev_task(
        db_session,
        project,
        titulo="Backlog Dev",
        created_by=pm_id,
        story_id=backlog_story.id,
        initial_state="to_do",
    )
    sprint_story = create_story_task(
        db_session,
        project,
        titulo="Sprint Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint_story.parent_id = sprint.id
    sprint_story.estado = "en_progreso"
    sprint_dev = create_dev_task(
        db_session,
        project,
        titulo="Sprint Dev",
        created_by=pm_id,
        story_id=sprint_story.id,
        initial_state="to_do",
    )
    epic.estado = "cerrada"
    db_session.flush()

    apply_scrum_parent_cascade(
        db_session,
        project,
        epic,
        target_state="cerrada",
        actor_user_id=pm_id,
        mode="cascade_backlog",
    )
    db_session.commit()
    db_session.refresh(backlog_story)
    db_session.refresh(backlog_dev)
    db_session.refresh(sprint_dev)

    assert backlog_story.estado == "completado"
    assert backlog_dev.estado == "completed"
    assert sprint_dev.estado == "to_do"


def test_epic_cascade_to_pendiente_via_story_target(db_session: Session):
    project, pm_id = _seed(db_session)
    sprint = create_sprint_record(
        db_session, project, created_by=pm_id, nombre="S1", orden=1
    )
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story.parent_id = sprint.id
    story.estado = "en_progreso"
    dev = create_dev_task(
        db_session,
        project,
        titulo="Dev",
        created_by=pm_id,
        story_id=story.id,
        initial_state="in_progress",
    )
    db_session.commit()

    from app.services.scrum_parent_cascade import resolve_cascade_target_state

    cascade_state = resolve_cascade_target_state(
        epic, target_state="abierta", cascade_target_state="pendiente"
    )
    assert cascade_state == "pendiente"

    apply_scrum_parent_cascade(
        db_session,
        project,
        epic,
        target_state=cascade_state,
        actor_user_id=pm_id,
        mode="all",
    )
    db_session.commit()
    db_session.refresh(story)
    db_session.refresh(dev)

    assert epic.estado == "abierta"
    assert story.estado == "pendiente"
    assert dev.estado == "to_do"


def test_epic_cascade_cancelado(db_session: Session):
    project, pm_id = _seed(db_session)
    sprint = create_sprint_record(
        db_session, project, created_by=pm_id, nombre="S1", orden=1
    )
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story.parent_id = sprint.id
    story.estado = "en_progreso"
    db_session.commit()

    apply_scrum_parent_cascade(
        db_session,
        project,
        epic,
        target_state="cancelado",
        actor_user_id=pm_id,
        mode="all",
    )
    db_session.commit()
    db_session.refresh(story)

    assert story.estado == "cancelado"
    assert epic.estado == "abierta"


def test_epic_move_same_state_with_cascade_target_via_transition(db_session: Session):
    project, pm_id = _seed(db_session)
    sprint = create_sprint_record(
        db_session, project, created_by=pm_id, nombre="S1", orden=1
    )
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story.parent_id = sprint.id
    story.estado = "en_progreso"
    db_session.commit()

    transition_record(
        db_session,
        project,
        epic,
        action_id="move",
        actor_user_id=pm_id,
        target_state="abierta",
        side_effect_context={"cascade_target_state": "pendiente", "cascade_mode": "all"},
    )
    db_session.commit()
    db_session.refresh(story)

    assert epic.estado == "abierta"
    assert story.estado == "pendiente"


def test_epic_cascade_all_commits_backlog_story_to_sprint(db_session: Session):
    project, pm_id = _seed(db_session)
    backlog = get_product_backlog_milestone(db_session, project.id)
    sprint = create_sprint_record(
        db_session, project, created_by=pm_id, nombre="S1", orden=1
    )
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    backlog_story = create_story_task(
        db_session,
        project,
        titulo="PB Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    backlog_story.parent_id = backlog.id
    backlog_story.estado = "product_backlog"
    sprint_story = create_story_task(
        db_session,
        project,
        titulo="Sprint Story",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint_story.parent_id = sprint.id
    sprint_story.estado = "en_progreso"
    db_session.commit()

    apply_scrum_parent_cascade(
        db_session,
        project,
        epic,
        target_state="pendiente",
        actor_user_id=pm_id,
        mode="all",
        side_effect_context={"sprint_id": str(sprint.id)},
    )
    db_session.commit()
    db_session.refresh(backlog_story)
    db_session.refresh(sprint_story)

    assert backlog_story.parent_id == sprint.id
    assert backlog_story.estado == "pendiente"
    assert sprint_story.estado == "pendiente"
