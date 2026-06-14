"""Tests sync dev, gate UAT y acciones de feature (§5.4–§5.6)."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.services.features import (
    apply_feature_action,
    load_active_tasks,
    uat_gate_status,
)
from app.services.tasks import move_task
from tests.record_helpers import seed_milestone_feature, seed_project_with_roles


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_project(session: Session):
    project, pm_id, dev_id, qa_id = seed_project_with_roles(session)
    milestone, feature = seed_milestone_feature(session, project, pm_id)
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
    )
    assert feature.estado == "uat"

    apply_feature_action(
        db_session,
        feature,
        project,
        action="enviar_al_pm",
        actor_user_id=qa_id,
    )
    assert feature.estado == "esperando_liberacion_pm"
    assert task.estado == "completed"

    apply_feature_action(
        db_session,
        feature,
        project,
        action="completar",
        actor_user_id=pm_id,
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
