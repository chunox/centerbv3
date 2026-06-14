"""Tests de categorías semánticas y allowed_role_slugs en workflow task."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.domain.workflow_templates import default_task_workflow
from app.models.entities import User
from app.services.project_roles import update_workflow_definition
from app.services.records.repository import create_record
from app.services.tasks import move_task
from app.services.workflow.categories import (
    task_test_state_keys,
    validate_task_state_categories,
)
from app.services.workflow.engine import apply_entity_transition
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org
from tests.record_helpers import create_feature_record, create_milestone_record


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


def test_task_test_state_keys_uses_category():
    wf = default_task_workflow()
    wf = {
        **wf,
        "states": [
            {**s, "key": "qa_ready", "category": "test"}
            if s["key"] == "ready_for_test"
            else s
            for s in wf["states"]
        ],
    }
    assert task_test_state_keys(wf) == frozenset({"qa_ready"})


def test_validate_task_state_categories_rejects_unknown():
    wf = default_task_workflow()
    wf["states"][0]["category"] = "inbox"
    with pytest.raises(ValueError, match="inválida"):
        validate_task_state_categories(wf)


def test_update_workflow_rejects_unknown_role_slug(db_session: Session):
    pm_id = uuid4()
    db_session.add(User(id=pm_id, nombre="PM", email="pm-wf@test", password_hash="x"))
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org)
    db_session.commit()

    defn = default_task_workflow()
    defn["transitions"] = [
        {
            **defn["transitions"][0],
            "from": ["backlog"],
            "to": "to_do",
            "allowed_role_slugs": ["no_existe"],
        },
        defn["transitions"][1],
    ]
    with pytest.raises(HTTPException) as exc:
        update_workflow_definition(db_session, project, "task", defn)
    assert exc.value.status_code == 422
    assert "no_existe" in str(exc.value.detail)


def test_move_task_respects_allowed_role_slugs(db_session: Session):
    pm_id = uuid4()
    dev_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm-roles@test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev-roles@test", password_hash="x"),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org)
    add_member_with_slug(db_session, project, dev_id, "dev")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        nombre="F roles",
        with_default_task=False,
    )
    feature.estado = "en_progreso"
    task = create_record(
        db_session,
        project,
        entity_type="task",
        titulo="T roles",
        created_by=pm_id,
        parent_id=feature.id,
        estado="backlog",
    )

    defn = default_task_workflow()
    defn["transitions"] = [
        {
            "id": "move",
            "label": "Mover",
            "from": ["backlog"],
            "to": "to_do",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["qa"],
        },
        defn["transitions"][1],
    ]
    wf, _ = update_workflow_definition(db_session, project, "task", defn)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        apply_entity_transition(
            db_session,
            project,
            task,
            entity_type="task",
            action_id="move",
            actor_user_id=dev_id,
            target_state="to_do",
        )
    assert exc.value.status_code in (403, 409)


def test_move_task_explicit_edge_wins_over_dynamic_move(db_session: Session):
    """Si coexisten move dinámico y arista explícita, solo aplica la explícita."""
    pm_id = uuid4()
    dev_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm-graph@test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev-graph@test", password_hash="x"),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org)
    add_member_with_slug(db_session, project, dev_id, "dev")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        nombre="F graph",
        with_default_task=False,
    )
    feature.estado = "en_progreso"
    task = create_record(
        db_session,
        project,
        entity_type="task",
        titulo="T graph",
        created_by=pm_id,
        parent_id=feature.id,
        estado="backlog",
    )

    defn = default_task_workflow()
    defn["transitions"] = [
        {
            "id": "move",
            "label": "→ Por hacer",
            "from": ["backlog"],
            "to": "to_do",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": ["pm"],
        },
        defn["transitions"][0],
        defn["transitions"][1],
    ]
    update_workflow_definition(db_session, project, "task", defn)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        move_task(
            db_session,
            task,
            feature,
            project,
            nuevo_estado="in_progress",
            actor_user_id=dev_id,
        )
    assert exc.value.status_code == 409

    move_task(
        db_session,
        task,
        feature,
        project,
        nuevo_estado="to_do",
        actor_user_id=pm_id,
    )
    assert task.estado == "to_do"


def test_explicit_move_empty_roles_denies_everyone(db_session: Session):
    pm_id = uuid4()
    dev_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm-empty@test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev-empty@test", password_hash="x"),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org)
    add_member_with_slug(db_session, project, dev_id, "dev")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        nombre="F empty roles",
        with_default_task=False,
    )
    feature.estado = "en_progreso"
    task = create_record(
        db_session,
        project,
        entity_type="task",
        titulo="T empty roles",
        created_by=pm_id,
        parent_id=feature.id,
        estado="backlog",
    )

    defn = default_task_workflow()
    defn["transitions"] = [
        {
            "id": "move",
            "label": "→ Por hacer",
            "from": ["backlog"],
            "to": "to_do",
            "required_capabilities": ["kanban.task.move"],
            "allowed_role_slugs": [],
        },
        defn["transitions"][1],
    ]
    update_workflow_definition(db_session, project, "task", defn)
    db_session.commit()

    with pytest.raises(HTTPException):
        move_task(
            db_session,
            task,
            feature,
            project,
            nuevo_estado="to_do",
            actor_user_id=dev_id,
        )
