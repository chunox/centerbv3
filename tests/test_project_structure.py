"""Tests de estructura de proyecto personalizable (fases libres)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import ProjectBlock
from app.schemas.project_structure import ProjectStructureDef, ProjectStructureEntity
from app.services.packs import ensure_system_packs, list_record_types, seed_project_from_pack
from app.services.project_structure import merge_pack_with_structure, validate_structure_entities
from app.services.records import generic_store
from tests.org_helpers import create_organization, create_project_for_org, create_user


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
        ensure_system_packs(session)
        yield session
    finally:
        session.close()


@pytest.fixture
def api_client(db_session: Session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_validate_structure_rejects_cycle():
    entities = [
        ProjectStructureEntity(key="a", label="A", parent_type_keys=["c"]),
        ProjectStructureEntity(key="b", label="B", parent_type_keys=["a"]),
        ProjectStructureEntity(key="c", label="C", parent_type_keys=["b"]),
    ]
    with pytest.raises(ValueError, match="ciclo"):
        validate_structure_entities(entities)


def test_merge_pack_custom_software_structure(db_session: Session):
    from app.domain.packs.catalog import get_pack_manifest

    base = get_pack_manifest("software")
    assert base is not None
    structure = ProjectStructureDef(
        entity_types=[
            ProjectStructureEntity(key="campana", label="Campaña", orden=1),
            ProjectStructureEntity(
                key="entregable",
                label="Entregable",
                parent_type_keys=["campana"],
                orden=2,
            ),
            ProjectStructureEntity(
                key="task",
                label="Tarea",
                parent_type_keys=["entregable"],
                traits={"kanban": True, "assignees": True},
                orden=3,
            ),
        ],
        initial_roots=[{"titulo": "Brief", "orden": 0}],
    )
    merged = merge_pack_with_structure(base, structure, template_slug="t3_interno_clasico")
    keys = {et.key for et in merged.entity_types}
    assert keys == {"campana", "entregable", "task"}
    assert "campana" in merged.workflows
    assert "task" in merged.workflows


def test_create_project_with_custom_structure(db_session: Session, api_client: TestClient):
    owner = create_user(db_session)
    org = create_organization(db_session, owner_id=owner.id)
    payload = {
        "organization_id": str(org.id),
        "nombre": "Marketing custom",
        "pack_slug": "software",
        "template_slug": "t3_interno_clasico",
        "fecha_inicio": "2026-01-01",
        "fecha_fin": "2026-12-31",
        "created_by": str(owner.id),
        "project_structure": {
            "entity_types": [
                {"key": "campana", "label": "Campaña", "orden": 1},
                {
                    "key": "entregable",
                    "label": "Entregable",
                    "parent_type_keys": ["campana"],
                    "orden": 2,
                },
                {
                    "key": "task",
                    "label": "Tarea",
                    "parent_type_keys": ["entregable"],
                    "traits": {"kanban": True},
                    "orden": 3,
                },
            ],
            "initial_roots": [{"titulo": "Lanzamiento Q1"}],
        },
    }
    response = api_client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]

    types = list_record_types(db_session, uuid.UUID(project_id))
    assert {t.key for t in types} == {"campana", "entregable", "task"}

    scope_block = db_session.scalar(
        select(ProjectBlock).where(
            ProjectBlock.project_id == uuid.UUID(project_id),
            ProjectBlock.key == "scope",
        )
    )
    assert scope_block is not None
    cfg = scope_block.config or {}
    assert cfg.get("root_entity_type") == "campana"
    assert "entregable" in (cfg.get("child_entity_types") or [])


def test_record_parent_validation(db_session: Session):
    pm = create_user(db_session)
    org = create_organization(db_session, owner_id=pm.id)
    from app.models.entities import Project

    project = Project(
        id=uuid.uuid4(),
        organization_id=org.id,
        nombre="P",
        template_slug="t3_interno_clasico",
        pack_slug="simple",
        fecha_inicio=__import__("datetime").date(2026, 1, 1),
        fecha_fin=__import__("datetime").date(2026, 12, 31),
        created_by=pm.id,
    )
    db_session.add(project)
    db_session.flush()
    structure = ProjectStructureDef(
        entity_types=[
            ProjectStructureEntity(key="fase", label="Etapa", orden=1),
            ProjectStructureEntity(
                key="tarea",
                label="Item",
                parent_type_keys=["fase"],
                orden=2,
            ),
        ]
    )
    seed_project_from_pack(
        db_session, project, "simple", template_slug="t5_freestyle", project_structure=structure
    )
    root = generic_store.create_record(
        db_session, project, record_type="fase", titulo="Fase 1", created_by=pm.id
    )
    child = generic_store.create_record(
        db_session,
        project,
        record_type="tarea",
        titulo="T1",
        created_by=pm.id,
        parent_id=root.id,
    )
    db_session.commit()
    assert child.parent_id == root.id


def test_entity_type_crud_api(db_session: Session, api_client: TestClient):
    pm = create_user(db_session)
    project = create_project_for_org(db_session, pm.id, pack_slug="software", tipo="interno")
    db_session.commit()

    create_resp = api_client.post(
        f"/api/v1/projects/{project.id}/entity-types",
        json={
            "actor_user_id": str(pm.id),
            "key": "brief",
            "label": "Brief",
            "parent_type_keys": ["milestone"],
            "orden": 3,
        },
    )
    assert create_resp.status_code == 201, create_resp.text

    patch_resp = api_client.patch(
        f"/api/v1/projects/{project.id}/entity-types/brief",
        json={"actor_user_id": str(pm.id), "label": "Brief creativo"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["label"] == "Brief creativo"

    delete_resp = api_client.request(
        "DELETE",
        f"/api/v1/projects/{project.id}/entity-types/brief",
        json={"actor_user_id": str(pm.id)},
    )
    assert delete_resp.status_code == 200
