"""Tests Scrum v2: sprint raíz, story/epic tasks."""
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
from app.services.records.generic_store import list_records, transition_record
from app.services.scrum_effort import get_scrum_item_sprint_id, is_record_in_product_backlog
from app.services.scrum_tasks import create_dev_subtask, create_dev_task, create_epic_task, create_story_task
from app.services.scrum_v2_structure import (
    get_product_backlog_milestone,
    list_stories_for_sprint,
    list_stories_in_backlog,
)
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
        nombre="Scrum V2 Test",
        estado="activo",
        created_by=pm_id,
        template_slug="t6_scrum_interno",
        pack_slug="software",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    dev_id = uuid4()
    session.add(
        User(
            id=dev_id,
            email="dev@test.local",
            nombre="Dev",
            password_hash="x",
        )
    )
    session.add(project)
    session.flush()
    seed_project_from_pack(session, project, "software", template_slug="t6_scrum_interno")
    add_member_with_slug(session, project, pm_id, "pm")
    add_member_with_slug(session, project, dev_id, "tech_lead")
    session.commit()
    return project, pm_id, dev_id


def test_product_backlog_record_and_epic_story_tasks(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    backlog = get_product_backlog_milestone(db_session, project.id)
    assert backlog is not None
    assert backlog.record_type == "product_backlog"

    epic = create_epic_task(db_session, project, titulo="Inventario", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia A",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    db_session.commit()

    assert story.parent_id == backlog.id
    assert is_record_in_product_backlog(db_session, story)
    assert len(list_stories_in_backlog(db_session, project.id)) == 1


def test_comprometer_sprint_reparents_story(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Ops", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Recepción",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint 1",
        orden=1,
        horas_planeadas=32,
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
    db_session.commit()
    db_session.refresh(story)

    assert story.parent_id == sprint.id
    assert story.estado == "pendiente"
    assert get_scrum_item_sprint_id(db_session, story) == sprint.id
    assert len(list_stories_for_sprint(db_session, project.id, sprint.id)) == 1
    assert len(list_stories_in_backlog(db_session, project.id)) == 0


def test_dev_task_rollup_stays_en_progreso_when_ready_for_test(db_session: Session):
    project, pm_id, dev_id = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia UAT",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint 2",
        orden=2,
    )
    db_session.commit()

    create_dev_task(
        db_session,
        project,
        titulo="Historia UAT",
        created_by=pm_id,
        story_id=story.id,
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
    from app.services.scrum_v2_structure import list_dev_tasks_for_story

    dev_tasks = list_dev_tasks_for_story(db_session, project.id, story.id)
    assert len(dev_tasks) == 1
    dev = dev_tasks[0]
    dev.estado = "ready_for_test"
    dev.data = {**(dev.data or {}), "estimacion_horas": 4}
    db_session.commit()
    db_session.refresh(story)

    assert story.estado != "en_progreso"


def test_dev_complete_does_not_auto_complete_story(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia done",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint 2",
        orden=2,
    )
    db_session.commit()

    create_dev_task(
        db_session,
        project,
        titulo="Task A",
        created_by=pm_id,
        story_id=story.id,
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
    from app.services.scrum_v2_structure import list_dev_tasks_for_story
    from app.services.scrum_tasks import sync_story_from_dev_tasks

    dev = list_dev_tasks_for_story(db_session, project.id, story.id)[0]
    transition_record(
        db_session,
        project,
        dev,
        action_id="move",
        actor_user_id=pm_id,
        target_state="completed",
    )
    db_session.commit()
    db_session.refresh(story)

    assert story.estado != "completado"


def test_dev_transition_syncs_sprint_horas_completadas(db_session: Session):
    """Completar la última dev task vía transition debe actualizar horas_completadas del sprint."""
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia métricas",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint métricas",
        orden=3,
        horas_planeadas=16,
    )
    db_session.commit()

    create_dev_task(
        db_session,
        project,
        titulo="Task horas",
        created_by=pm_id,
        story_id=story.id,
        data={"estimacion_horas": 8},
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
    from app.services.scrum_v2_structure import list_dev_tasks_for_story

    dev = list_dev_tasks_for_story(db_session, project.id, story.id)[0]
    assert sprint.data.get("horas_completadas", 0) == 0

    transition_record(
        db_session,
        project,
        dev,
        action_id="move",
        actor_user_id=pm_id,
        target_state="completed",
    )
    story.estado = "en_progreso"
    db_session.flush()
    transition_record(
        db_session,
        project,
        story,
        action_id="completar",
        actor_user_id=pm_id,
    )
    db_session.commit()
    db_session.refresh(story)
    db_session.refresh(sprint)

    assert story.estado == "completado"
    assert sprint.data.get("horas_completadas") == 8.0


def test_completar_story_closes_open_dev_tasks(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia manual",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint 2",
        orden=2,
    )
    db_session.commit()

    create_dev_task(
        db_session,
        project,
        titulo="Task review",
        created_by=pm_id,
        story_id=story.id,
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
    from app.services.scrum_v2_structure import list_dev_tasks_for_story

    dev = list_dev_tasks_for_story(db_session, project.id, story.id)[0]
    dev.estado = "ready_for_test"
    db_session.flush()
    story.estado = "en_progreso"
    db_session.flush()

    transition_record(
        db_session,
        project,
        story,
        action_id="completar",
        actor_user_id=pm_id,
    )
    db_session.commit()
    db_session.refresh(story)
    db_session.refresh(dev)

    assert story.estado == "completado"
    assert dev.estado == "completed"


def test_cancel_story_cascades_dev_tasks(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia cancel",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint cancel",
        orden=4,
    )
    db_session.commit()

    create_dev_task(
        db_session,
        project,
        titulo="Dev A",
        created_by=pm_id,
        story_id=story.id,
    )
    create_dev_task(
        db_session,
        project,
        titulo="Dev B",
        created_by=pm_id,
        story_id=story.id,
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
    from app.services.scrum_v2_structure import list_dev_tasks_for_story

    dev_tasks = list_dev_tasks_for_story(db_session, project.id, story.id)
    assert len(dev_tasks) == 2

    transition_record(
        db_session,
        project,
        story,
        action_id="cancelar",
        actor_user_id=pm_id,
    )
    db_session.commit()

    for dev in dev_tasks:
        db_session.refresh(dev)
        assert dev.estado == "cancel"
    db_session.refresh(story)
    assert story.estado == "cancelado"


def test_pm_move_story_to_cancelado_cascades_dev_tasks(db_session: Session):
    """Drag-drop de historia a Cancelado usa action move (PM) y debe cancelar tareas dev."""
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia move cancel",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint move cancel",
        orden=5,
    )
    db_session.commit()

    dev = create_dev_task(
        db_session,
        project,
        titulo="Dev move",
        created_by=pm_id,
        story_id=story.id,
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
    db_session.commit()

    transition_record(
        db_session,
        project,
        story,
        action_id="move",
        actor_user_id=pm_id,
        target_state="cancelado",
        side_effect_context={"cascade_mode": "all"},
    )
    db_session.commit()
    db_session.refresh(story)
    db_session.refresh(dev)

    assert story.estado == "cancelado"
    assert dev.estado == "cancel"


def test_epic_does_not_auto_close_when_stories_done(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story_a = create_story_task(
        db_session,
        project,
        titulo="A",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story_b = create_story_task(
        db_session,
        project,
        titulo="B",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    db_session.commit()

    story_a.estado = "completado"
    story_b.estado = "completado"
    db_session.flush()

    from app.services.scrum_tasks import sync_epic_from_stories

    sync_epic_from_stories(db_session, epic, project, actor_user_id=pm_id)
    db_session.commit()
    db_session.refresh(epic)

    assert epic.estado == "abierta"


def test_epic_cerrar_cascades_open_stories(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic gate", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Abierta",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story.estado = "en_progreso"
    db_session.commit()

    transition_record(
        db_session,
        project,
        epic,
        action_id="cerrar",
        actor_user_id=pm_id,
    )
    db_session.commit()
    db_session.refresh(epic)
    db_session.refresh(story)

    assert epic.estado == "cerrada"
    assert story.estado == "completado"


def test_epic_cerrar_allowed_when_all_stories_terminal(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic ok", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Hecha",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story.estado = "completado"
    db_session.commit()

    transition_record(
        db_session,
        project,
        epic,
        action_id="cerrar",
        actor_user_id=pm_id,
    )
    db_session.commit()
    db_session.refresh(epic)

    assert epic.estado == "cerrada"


def test_epic_sync_abierta_while_stories_active(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
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

    transition_record(
        db_session,
        project,
        story,
        action_id="comprometer_sprint",
        actor_user_id=pm_id,
        side_effect_context={"sprint_id": str(sprint.id)},
    )
    db_session.commit()
    db_session.refresh(epic)

    assert epic.estado == "abierta"


def test_subtask_rollup_completado(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic sub", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia subtareas",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint sub",
        orden=5,
    )
    db_session.commit()

    dev = create_dev_task(
        db_session,
        project,
        titulo="Dev padre",
        created_by=pm_id,
        story_id=story.id,
    )
    sub = create_dev_subtask(
        db_session,
        project,
        titulo="Subtarea",
        created_by=pm_id,
        parent_dev_id=dev.id,
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

    transition_record(
        db_session,
        project,
        dev,
        action_id="move",
        actor_user_id=pm_id,
        target_state="completed",
    )
    transition_record(
        db_session,
        project,
        sub,
        action_id="move",
        actor_user_id=pm_id,
        target_state="completed",
    )
    db_session.commit()
    db_session.refresh(story)

    assert story.estado != "completado"


def test_story_completar_cascades_subtasks(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic cascade", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia cascade sub",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint cascade sub",
        orden=6,
    )
    db_session.commit()

    dev = create_dev_task(
        db_session,
        project,
        titulo="Dev",
        created_by=pm_id,
        story_id=story.id,
        initial_state="in_progress",
    )
    sub = create_dev_subtask(
        db_session,
        project,
        titulo="Sub",
        created_by=pm_id,
        parent_dev_id=dev.id,
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

    transition_record(
        db_session,
        project,
        story,
        action_id="completar",
        actor_user_id=pm_id,
    )
    db_session.commit()
    db_session.refresh(dev)
    db_session.refresh(sub)

    assert dev.estado == "completed"
    assert sub.estado == "completed"


def test_cancel_story_cascades_subtasks(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic cancel sub", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia cancel sub",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    sprint = create_sprint_record(
        db_session,
        project,
        created_by=pm_id,
        nombre="Sprint cancel sub",
        orden=7,
    )
    db_session.commit()

    dev = create_dev_task(
        db_session,
        project,
        titulo="Dev",
        created_by=pm_id,
        story_id=story.id,
    )
    sub = create_dev_subtask(
        db_session,
        project,
        titulo="Sub",
        created_by=pm_id,
        parent_dev_id=dev.id,
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
    transition_record(
        db_session,
        project,
        story,
        action_id="cancelar",
        actor_user_id=pm_id,
    )
    db_session.commit()
    db_session.refresh(dev)
    db_session.refresh(sub)

    assert dev.estado == "cancel"
    assert sub.estado == "cancel"


def test_create_story_does_not_spawn_dev_task(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    from app.services.scrum_v2_structure import list_dev_tasks_for_story

    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia sin tarea auto",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    db_session.commit()

    dev_tasks = list_dev_tasks_for_story(db_session, project.id, story.id)
    assert dev_tasks == []


def test_in_product_backlog_list_filter(db_session: Session):
    project, pm_id, _ = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="E", created_by=pm_id)
    create_story_task(
        db_session,
        project,
        titulo="BL",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    db_session.commit()

    rows = list_records(
        db_session,
        project.id,
        record_type="task",
        in_product_backlog=True,
    )
    assert len(rows) == 1
    assert rows[0].titulo == "BL"


def test_scrum_rejects_task_dependency_on_epic(db_session: Session):
    from fastapi import HTTPException

    from app.services.task_dependencies import create_dependency

    project, pm_id, dev_id = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    db_session.commit()
    dev = create_dev_task(
        db_session,
        project,
        titulo="Tarea dev",
        created_by=pm_id,
        story_id=story.id,
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        create_dependency(
            db_session,
            project,
            epic,
            dev,
            actor_user_id=dev_id,
        )
    assert exc.value.status_code == 400
    assert "historias" in exc.value.detail.lower()


def test_scrum_rejects_cross_story_task_on_story(db_session: Session):
    from fastapi import HTTPException

    from app.services.task_dependencies import create_dependency

    project, pm_id, dev_id = _seed_scrum_project(db_session)
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story_a = create_story_task(
        db_session,
        project,
        titulo="A",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    story_b = create_story_task(
        db_session,
        project,
        titulo="B",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    db_session.commit()
    dev_b = create_dev_task(
        db_session,
        project,
        titulo="Tarea B",
        created_by=pm_id,
        story_id=story_b.id,
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        create_dependency(
            db_session,
            project,
            story_a,
            dev_b,
            actor_user_id=dev_id,
        )
    assert exc.value.status_code == 400


def test_scrum_dev_task_move_via_transition_api(db_session: Session, api_client):
    from app.domain.capabilities import KANBAN_TASK_MOVE
    from app.services.role_capabilities import ensure_role_capabilities
    from tests.conftest import auth_headers

    project, pm_id, _dev_id = _seed_scrum_project(db_session)
    ensure_role_capabilities(db_session, project.id, "pm", [KANBAN_TASK_MOVE])
    epic = create_epic_task(db_session, project, titulo="Epic", created_by=pm_id)
    story = create_story_task(
        db_session,
        project,
        titulo="Historia",
        created_by=pm_id,
        epic_task_id=epic.id,
    )
    dev = create_dev_task(
        db_session,
        project,
        titulo="Implementar",
        created_by=pm_id,
        story_id=story.id,
    )
    db_session.commit()

    res = api_client.post(
        f"/api/v1/projects/{project.id}/records/{dev.id}/transition",
        json={"action_id": "move", "target_state": "in_progress"},
        headers=auth_headers(pm_id, project.organization_id),
    )
    assert res.status_code == 200, res.text
    assert res.json()["estado"] == "in_progress"
