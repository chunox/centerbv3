"""Tests: sync de capabilities al guardar workflow."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.domain.packs.catalog import get_pack_manifest
from app.models.entities import Project
from app.services.packs import ensure_system_packs, seed_project_from_pack
from app.services.project_roles import get_role_capabilities, list_project_roles, update_workflow_definition
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


def _simple_project(db_session: Session) -> Project:
    ensure_system_packs(db_session)
    user = create_user(db_session)
    org = create_organization(db_session, owner_id=user.id)
    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        nombre="Cap sync test",
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
    return project


def test_workflow_save_syncs_transition_caps_to_owner(db_session: Session):
    project = _simple_project(db_session)
    manifest = get_pack_manifest("simple")
    defn = dict(manifest.workflow_profiles["default"]["tarea"])
    defn["transitions"] = list(defn["transitions"]) + [
        {
            "id": "reabrir",
            "label": "Reabrir",
            "from": ["hecho"],
            "to": "pendiente",
            "required_capabilities": ["record.tarea.transition.reabrir"],
            "enabled": True,
        }
    ]

    _wf, added = update_workflow_definition(db_session, project, "tarea", defn)
    db_session.commit()

    assert "record.tarea.transition.reabrir" in added
    owner = next(r for r in list_project_roles(db_session, project.id) if r.slug == "owner")
    caps = get_role_capabilities(db_session, owner.id)
    assert "record.tarea.transition.reabrir" in caps


def test_workflow_save_caps_only_on_allowed_roles(db_session: Session):
    project = _simple_project(db_session)
    from app.models.entities import ProjectRole, ProjectRoleCapability

    cliente = ProjectRole(
        project_id=project.id,
        slug="cliente",
        nombre="Cliente",
        is_system=False,
        orden=99,
    )
    db_session.add(cliente)
    db_session.flush()
    db_session.add(
        ProjectRoleCapability(role_id=cliente.id, capability_key="record.tarea.read")
    )
    db_session.commit()

    manifest = get_pack_manifest("simple")
    defn = dict(manifest.workflow_profiles["default"]["tarea"])
    defn["transitions"] = [
        {
            "id": "aprobar_cliente",
            "label": "Aprobar",
            "from": ["pendiente"],
            "to": "en_curso",
            "required_capabilities": ["record.tarea.transition.aprobar_cliente"],
            "allowed_role_slugs": ["cliente"],
            "enabled": True,
        }
    ]

    _wf, added = update_workflow_definition(db_session, project, "tarea", defn)
    db_session.commit()

    assert "record.tarea.transition.aprobar_cliente" in added
    owner = next(r for r in list_project_roles(db_session, project.id) if r.slug == "owner")
    cliente_role = next(r for r in list_project_roles(db_session, project.id) if r.slug == "cliente")
    assert "record.tarea.transition.aprobar_cliente" not in get_role_capabilities(
        db_session, owner.id
    )
    assert "record.tarea.transition.aprobar_cliente" in get_role_capabilities(
        db_session, cliente_role.id
    )


def test_workflow_save_skips_cap_sync_when_graph_edge_has_no_roles(db_session: Session):
    project = _simple_project(db_session)
    defn = {
        "states": [
            {"key": "pendiente", "label": "Pendiente", "category": "pending"},
            {"key": "en_curso", "label": "En curso", "category": "active"},
            {"key": "hecho", "label": "Hecho", "category": "done", "is_terminal": True},
        ],
        "initial_state": "pendiente",
        "terminal_states": ["hecho"],
        "transitions": [
            {
                "id": "move",
                "label": "→ En curso",
                "from": ["pendiente"],
                "to": "en_curso",
                "required_capabilities": ["record.tarea.transition.move"],
                "allowed_role_slugs": [],
            }
        ],
    }

    _wf, added = update_workflow_definition(db_session, project, "tarea", defn)
    db_session.commit()

    assert added == []
    owner = next(r for r in list_project_roles(db_session, project.id) if r.slug == "owner")
    assert "record.tarea.transition.move" not in get_role_capabilities(db_session, owner.id)
