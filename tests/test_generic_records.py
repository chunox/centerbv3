"""Tests del gestor genérico: packs y project_records."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base

from app.domain.packs.catalog import get_pack_manifest
from app.models.entities import ProjectRecord
from app.services.packs import ensure_system_packs, seed_project_from_pack
from app.services.records import generic_store
from tests.org_helpers import create_organization, create_user


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


def test_system_packs_seeded(db_session: Session):
    ensure_system_packs(db_session)
    db_session.commit()
    manifest = get_pack_manifest("simple")
    assert manifest is not None
    assert manifest.slug == "simple"
    assert any(et.key == "tarea" for et in manifest.entity_types)


def test_create_generic_project_with_evento_pack(db_session: Session):
    ensure_system_packs(db_session)
    user = create_user(db_session)
    org = create_organization(db_session, owner_id=user.id)
    from app.models.entities import Project

    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        nombre="Fiesta",
        template_slug="default",
        pack_slug="evento",
        fecha_inicio=__import__("datetime").date(2026, 6, 1),
        fecha_fin=__import__("datetime").date(2026, 6, 30),
        created_by=user.id,
    )
    db_session.add(project)
    db_session.flush()
    roles = seed_project_from_pack(db_session, project, "evento")
    db_session.commit()
    assert "coordinador" in roles
    record = generic_store.create_record(
        db_session,
        project,
        record_type="tarea",
        titulo="Contratar DJ",
        created_by=user.id,
    )
    db_session.commit()
    assert record.estado == "pendiente"
    assert record.record_type == "tarea"
    row = db_session.get(ProjectRecord, record.id)
    assert row is not None


def test_simple_pack_seeds_board_workbench(db_session: Session):
    ensure_system_packs(db_session)
    user = create_user(db_session)
    org = create_organization(db_session, owner_id=user.id)
    from app.models.entities import Project, ProjectWorkbenchDefinition
    from app.services.blocks import list_project_blocks

    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        nombre="Tablero simple",
        template_slug="default",
        pack_slug="simple",
        fecha_inicio=__import__("datetime").date(2026, 1, 1),
        fecha_fin=__import__("datetime").date(2026, 12, 31),
        created_by=user.id,
    )
    db_session.add(project)
    db_session.flush()
    seed_project_from_pack(db_session, project, "simple")
    db_session.commit()

    blocks = {b.key: b for b in list_project_blocks(db_session, project.id)}
    assert "board" in blocks
    assert blocks["board"].config.get("view_type") == "board"
    assert blocks["board"].config.get("entity_type_key") == "tarea"

    wb_row = db_session.scalar(
        __import__("sqlalchemy").select(ProjectWorkbenchDefinition).where(
            ProjectWorkbenchDefinition.project_id == project.id
        )
    )
    assert wb_row is not None
    workbenches = (
        wb_row.definition
        if isinstance(wb_row.definition, list)
        else __import__("json").loads(wb_row.definition)
    )
    board_wb = next(w for w in workbenches if w["key"] == "board")
    assert board_wb["view_type"] == "board"
    assert board_wb["entity_type"] == "tarea"


def test_record_transition_simple_pack(db_session: Session):
    ensure_system_packs(db_session)
    user = create_user(db_session)
    org = create_organization(db_session, owner_id=user.id)
    from app.models.entities import Project

    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        nombre="Personal",
        template_slug="default",
        pack_slug="simple",
        fecha_inicio=__import__("datetime").date(2026, 1, 1),
        fecha_fin=__import__("datetime").date(2026, 12, 31),
        created_by=user.id,
    )
    db_session.add(project)
    db_session.flush()
    roles = seed_project_from_pack(db_session, project, "simple")
    from app.models.entities import ProjectMember

    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            role_id=roles["owner"].id,
        )
    )
    db_session.commit()

    dto = generic_store.create_record(
        db_session,
        project,
        record_type="tarea",
        titulo="Comprar materiales",
        created_by=user.id,
    )
    row = db_session.get(ProjectRecord, dto.id)
    assert row is not None
    updated = generic_store.transition_record(
        db_session,
        project,
        row,
        action_id="iniciar",
        actor_user_id=user.id,
    )
    db_session.commit()
    assert updated.estado == "en_curso"


def test_import_pack_config(db_session: Session):
    ensure_system_packs(db_session)
    user = create_user(db_session)
    org = create_organization(db_session, owner_id=user.id)
    from app.models.entities import Project

    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        nombre="Import test",
        template_slug="default",
        pack_slug="simple",
        fecha_inicio=__import__("datetime").date(2026, 1, 1),
        fecha_fin=__import__("datetime").date(2026, 12, 31),
        created_by=user.id,
    )
    db_session.add(project)
    db_session.flush()
    seed_project_from_pack(db_session, project, "simple")
    db_session.commit()

    from app.services.packs import import_project_pack_config

    wf = get_pack_manifest("simple").workflows["tarea"]
    import_project_pack_config(
        db_session,
        project,
        {
            "pack_slug": "simple",
            "workflows": {"tarea": wf},
            "workbenches": [
                {
                    "key": "checklist",
                    "label": "Lista",
                    "route": "v/checklist",
                    "view_type": "checklist",
                    "entity_type": "tarea",
                    "required_capabilities": ["workbench.checklist"],
                    "orden": 10,
                }
            ],
        },
    )
    db_session.commit()

    from app.services.workflow.store import get_workbenches

    wbs = get_workbenches(db_session, project.id)
    assert any(wb["label"] == "Lista" for wb in wbs)


def test_transition_record_blocked_by_dependency(db_session: Session):
    from fastapi import HTTPException

    from app.services.records.repository import create_record
    from app.services.task_dependencies import create_dependency
    from tests.record_helpers import (
        create_feature_record,
        create_milestone_record,
        seed_project_with_roles,
    )

    project, pm_id, dev_id, _ = seed_project_with_roles(db_session)
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        with_default_task=False,
    )
    pred = create_record(
        db_session,
        project,
        entity_type="task",
        titulo="Predecesora",
        created_by=dev_id,
        parent_id=feature.id,
        estado="in_progress",
    )
    succ = create_record(
        db_session,
        project,
        entity_type="task",
        titulo="Sucesora",
        created_by=dev_id,
        parent_id=feature.id,
        estado="backlog",
    )
    create_dependency(db_session, project, succ, pred, actor_user_id=dev_id)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        generic_store.transition_record(
            db_session,
            project,
            succ,
            action_id="move",
            actor_user_id=dev_id,
            target_state="to_do",
        )
    assert exc.value.status_code == 409
