"""Tests sync dev, gate UAT y acciones de feature (§5.4–§5.6)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import (
    Feature,
    Milestone,
    Project,
    ProjectMember,
    Task,
    TaskStateTransition,
    User,
)
from app.services.features import (
    apply_feature_action,
    ensure_default_task,
    load_active_tasks,
    uat_gate_status,
)
from app.services.tasks import move_task
from tests.org_helpers import create_organization


def _seed_task_transitions(session: Session) -> None:
    pairs = [
        ("backlog", "to_do"),
        ("to_do", "in_progress"),
        ("in_progress", "ready_for_test"),
        ("ready_for_test", "in_progress"),
        ("ready_for_test", "completed"),
        ("completed", "in_progress"),
    ]
    for desde, hasta in pairs:
        session.add(
            TaskStateTransition(
                estado_desde=desde,
                estado_hasta=hasta,
                rol_permitido="dev",
            )
        )
    session.commit()


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    _seed_task_transitions(session)
    try:
        yield session
    finally:
        session.close()


def _seed_project(session: Session):
    pm_id = uuid4()
    dev_id = uuid4()
    qa_id = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@wf.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@wf.test", password_hash="x"),
            User(id=qa_id, nombre="QA", email="qa@wf.test", password_hash="x"),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="WF",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.add_all(
        [
            ProjectMember(project_id=project.id, user_id=pm_id, rol="pm"),
            ProjectMember(project_id=project.id, user_id=dev_id, rol="dev"),
            ProjectMember(project_id=project.id, user_id=qa_id, rol="qa"),
        ]
    )
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        created_by=pm_id,
    )
    session.add(milestone)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(feature)
    ensure_default_task(session, feature, created_by=pm_id)
    session.commit()
    return project, feature, milestone, pm_id, dev_id, qa_id


def test_sync_pendiente_to_en_progreso(db_session: Session):
    project, feature, _, pm_id, dev_id, _ = _seed_project(db_session)
    task = load_active_tasks(db_session, feature.id)[0]

    move_task(
        db_session,
        task,
        feature,
        project,
        nuevo_estado="to_do",
        actor_user_id=dev_id,
    )
    assert feature.estado == "en_progreso"


def test_uat_gate_and_pasar_a_uat(db_session: Session):
    project, feature, _, pm_id, dev_id, qa_id = _seed_project(db_session)
    task = load_active_tasks(db_session, feature.id)[0]

    for estado in ("to_do", "in_progress", "ready_for_test"):
        move_task(
            db_session,
            task,
            feature,
            project,
            nuevo_estado=estado,
            actor_user_id=dev_id,
        )

    gate = uat_gate_status(feature, load_active_tasks(db_session, feature.id))
    assert gate["can_pass_to_uat"] is True

    apply_feature_action(
        db_session,
        feature,
        project,
        action="pasar_a_uat",
        actor_user_id=dev_id,
        actor_rol="dev",
    )
    assert feature.estado == "uat"

    apply_feature_action(
        db_session,
        feature,
        project,
        action="enviar_al_pm",
        actor_user_id=qa_id,
        actor_rol="qa",
    )
    assert feature.estado == "esperando_liberacion_pm"
    assert task.estado == "completed"

    apply_feature_action(
        db_session,
        feature,
        project,
        action="completar",
        actor_user_id=pm_id,
        actor_rol="pm",
    )
    assert feature.estado == "completado"


def test_pasar_a_uat_blocked_when_not_all_ready(db_session: Session):
    project, feature, _, _, dev_id, _ = _seed_project(db_session)
    task = load_active_tasks(db_session, feature.id)[0]
    move_task(
        db_session,
        task,
        feature,
        project,
        nuevo_estado="to_do",
        actor_user_id=dev_id,
    )

    with pytest.raises(HTTPException) as exc:
        apply_feature_action(
            db_session,
            feature,
            project,
            action="pasar_a_uat",
            actor_user_id=dev_id,
            actor_rol="dev",
        )
    assert exc.value.status_code == 409


def test_cancel_feature_cascades_tasks(db_session: Session):
    project, feature, _, pm_id, dev_id, _ = _seed_project(db_session)
    task = load_active_tasks(db_session, feature.id)[0]
    move_task(
        db_session,
        task,
        feature,
        project,
        nuevo_estado="to_do",
        actor_user_id=dev_id,
    )

    apply_feature_action(
        db_session,
        feature,
        project,
        action="cancelar",
        actor_user_id=pm_id,
        actor_rol="pm",
    )
    assert feature.estado == "cancelado"
    assert task.estado == "cancel"


def test_sync_drops_uat_when_task_moves_back(db_session: Session):
    project, feature, _, _, dev_id, qa_id = _seed_project(db_session)
    task = load_active_tasks(db_session, feature.id)[0]
    for estado in ("to_do", "in_progress", "ready_for_test"):
        move_task(
            db_session,
            task,
            feature,
            project,
            nuevo_estado=estado,
            actor_user_id=dev_id,
        )
    apply_feature_action(
        db_session,
        feature,
        project,
        action="pasar_a_uat",
        actor_user_id=dev_id,
        actor_rol="dev",
    )
    move_task(
        db_session,
        task,
        feature,
        project,
        nuevo_estado="in_progress",
        actor_user_id=dev_id,
    )
    assert feature.estado == "en_progreso"
