"""Tests unitarios para validación de seed Scrum demo."""
from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import select

from app.models.entities import Project, ProjectRecord, User
from app.services.packs import seed_project_from_pack
from app.services.scrum_metrics import (
    sync_sprint_horas_completadas,
    sync_sprint_horas_planeadas,
)
from app.services.audit import record_audit_log
from app.services.scrum_seed_validation import (
    T6_TEMPLATE,
    validate_demo_scrum_seed,
    validate_project_scrum_seed,
)
from app.services.scrum_v2_structure import ensure_product_backlog_record, is_scrum_dev_task
from tests.org_helpers import add_member_with_slug, create_organization


def _seed_minimal_t6(session):
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
        nombre="Logistics Hub",
        template_slug=T6_TEMPLATE,
        pack_slug="software-scrum",
        created_by=pm_id,
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    session.add(project)
    session.flush()
    seed_project_from_pack(session, project, "software-scrum", template_slug=T6_TEMPLATE)
    add_member_with_slug(session, project, pm_id, "pm")
    backlog = ensure_product_backlog_record(session, project, created_by=pm_id)
    epic = ProjectRecord(
        id=uuid4(),
        project_id=project.id,
        record_type="task",
        parent_id=backlog.id,
        titulo="Inventario",
        estado="abierta",
        created_by=pm_id,
        data={"scrum_role": "epic"},
    )
    sprint = ProjectRecord(
        id=uuid4(),
        project_id=project.id,
        record_type="sprint",
        titulo="Sprint 1",
        estado="completado",
        created_by=pm_id,
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 1, 14),
        data={"sprint_goal": "Demo"},
    )
    story = ProjectRecord(
        id=uuid4(),
        project_id=project.id,
        record_type="task",
        parent_id=sprint.id,
        titulo="Historia demo",
        estado="completado",
        created_by=pm_id,
        data={
            "scrum_role": "story",
            "epic_task_id": str(epic.id),
            "prioridad": "alta",
        },
    )
    dev = ProjectRecord(
        id=uuid4(),
        project_id=project.id,
        record_type="task",
        parent_id=sprint.id,
        titulo="Dev task",
        estado="completed",
        created_by=pm_id,
        data={
            "scrum_role": "dev",
            "parent_task_id": str(story.id),
            "estimacion_horas": 8,
        },
    )
    session.add_all([epic, sprint, story, dev])
    session.flush()
    sync_sprint_horas_planeadas(session, sprint, commit=False)
    sync_sprint_horas_completadas(session, sprint, commit=False)
    record_audit_log(
        session,
        project_id=project.id,
        user_id=pm_id,
        entidad_tipo="tarea",
        entidad_id=story.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior="en_progreso",
        valor_nuevo="completado (completar)",
    )
    session.commit()
    return project


def test_validate_project_ok_minimal_hierarchy(db_session):
    project = _seed_minimal_t6(db_session)
    result = validate_project_scrum_seed(
        db_session,
        project,
        expected_epics=1,
        expected_sprints=1,
        expected_backlog_stories=0,
        expected_sprint_story_counts={1: 1},
    )
    assert result.ok, [f"{i.check}: {i.message}" for i in result.issues]
    assert result.counts["dev_tasks"] == 1


def test_validate_accepts_nested_dev(db_session):
    project = _seed_minimal_t6(db_session)
    sprint = db_session.scalar(
        select(ProjectRecord).where(
            ProjectRecord.project_id == project.id,
            ProjectRecord.record_type == "sprint",
        )
    )
    parent_dev = next(
        r
        for r in db_session.scalars(
            select(ProjectRecord).where(ProjectRecord.project_id == project.id)
        )
        if is_scrum_dev_task(r)
    )
    nested = ProjectRecord(
        id=uuid4(),
        project_id=project.id,
        record_type="task",
        parent_id=sprint.id,
        titulo="Subtarea",
        estado="completed",
        created_by=project.created_by,
        data={
            "scrum_role": "dev",
            "parent_task_id": str(parent_dev.id),
            "estimacion_horas": 2,
        },
    )
    db_session.add(nested)
    db_session.flush()
    from app.services.scrum_metrics import (
        sync_sprint_horas_completadas,
        sync_sprint_horas_planeadas,
    )

    sync_sprint_horas_planeadas(db_session, sprint, commit=False)
    sync_sprint_horas_completadas(db_session, sprint, commit=False)
    db_session.commit()

    result = validate_project_scrum_seed(
        db_session,
        project,
        expected_epics=1,
        expected_sprints=1,
        expected_backlog_stories=0,
        expected_sprint_story_counts={1: 1},
    )
    assert result.ok, [f"{i.check}: {i.message}" for i in result.issues]
    assert not any(i.check == "hierarchy.nested_dev" for i in result.issues)
    assert result.counts["nested_dev_tasks"] == 1
    assert result.counts["dev_tasks"] == 2


def test_validate_demo_scrum_missing_projects(db_session):
    report = validate_demo_scrum_seed(db_session)
    assert not report.ok
    assert len(report.results) == 2


def test_validate_warns_open_dev_on_completed_story(db_session):
    project = _seed_minimal_t6(db_session)
    dev = next(
        r
        for r in db_session.scalars(
            select(ProjectRecord).where(ProjectRecord.project_id == project.id)
        )
        if is_scrum_dev_task(r)
    )
    dev.estado = "ready_for_test"
    db_session.commit()

    result = validate_project_scrum_seed(
        db_session,
        project,
        expected_epics=1,
        expected_sprints=1,
        expected_backlog_stories=0,
        expected_sprint_story_counts={1: 1},
    )
    assert result.ok
    assert any(i.check == "sync.dev_done" and i.severity == "warning" for i in result.issues)
