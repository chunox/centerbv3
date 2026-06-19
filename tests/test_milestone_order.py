"""Orden de hitos: crear al final, recompactar al borrar, reordenar por PATCH."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Project, ProjectRecord
from app.schemas.milestones import MilestoneUpdate
from app.services.deletions import delete_milestone
from app.services.milestones import (
    compact_milestone_ordenes,
    next_milestone_orden,
    reorder_milestone,
    update_milestone,
)
from tests.org_helpers import create_organization, create_project_for_org
from tests.record_helpers import create_milestone_record


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


def _seed_project(session: Session):
    pm_id = uuid4()
    from app.models.entities import User

    session.add(User(id=pm_id, nombre="PM", email="pm@order.test", password_hash="x"))
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(session, pm_id, org, nombre="Proyecto")
    session.commit()
    return project, pm_id


def _add_milestone(
    session: Session, project: Project, pm_id, nombre: str, orden: int
) -> ProjectRecord:
    milestone = create_milestone_record(
        session, project, created_by=pm_id, nombre=nombre, orden=orden
    )
    session.commit()
    return milestone


def test_compact_milestone_ordenes_cierra_huecos(db_session: Session):
    project, pm_id = _seed_project(db_session)
    _add_milestone(db_session, project, pm_id, "H1", 1)
    _add_milestone(db_session, project, pm_id, "H3", 3)

    compact_milestone_ordenes(db_session, project.id)
    db_session.commit()

    from app.services.milestones import _ordered_milestones

    assert [m.orden for m in _ordered_milestones(db_session, project.id)] == [1, 2]


def test_next_milestone_orden_append(db_session: Session):
    project, pm_id = _seed_project(db_session)
    _add_milestone(db_session, project, pm_id, "H1", 1)
    _add_milestone(db_session, project, pm_id, "H2", 2)

    assert next_milestone_orden(db_session, project.id) == 3


def test_delete_middle_recompacta(db_session: Session):
    project, pm_id = _seed_project(db_session)
    h1 = _add_milestone(db_session, project, pm_id, "H1", 1)
    h2 = _add_milestone(db_session, project, pm_id, "H2", 2)
    _add_milestone(db_session, project, pm_id, "H3", 3)

    delete_milestone(db_session, h2, project, actor_user_id=pm_id)
    db_session.commit()

    from app.services.milestones import _ordered_milestones

    rows = _ordered_milestones(db_session, project.id)
    assert [m.titulo for m in rows] == ["H1", "H3"]
    assert [m.orden for m in rows] == [1, 2]
    assert next_milestone_orden(db_session, project.id) == 3
    assert h1.orden == 1


def test_reorder_milestone_intercambia_posiciones(db_session: Session):
    project, pm_id = _seed_project(db_session)
    h1 = _add_milestone(db_session, project, pm_id, "H1", 1)
    h2 = _add_milestone(db_session, project, pm_id, "H2", 2)
    h3 = _add_milestone(db_session, project, pm_id, "H3", 3)

    reorder_milestone(db_session, project.id, h3.id, 1, actor_user_id=pm_id)
    db_session.commit()

    from app.services.milestones import _ordered_milestones

    rows = _ordered_milestones(db_session, project.id)
    assert [m.id for m in rows] == [h3.id, h1.id, h2.id]
    assert [m.orden for m in rows] == [1, 2, 3]


def test_patch_orden_via_update_milestone(db_session: Session):
    project, pm_id = _seed_project(db_session)
    h1 = _add_milestone(db_session, project, pm_id, "H1", 1)
    h2 = _add_milestone(db_session, project, pm_id, "H2", 2)

    update_milestone(
        db_session,
        h2,
        project,
        MilestoneUpdate(actor_user_id=pm_id, orden=1),
    )
    db_session.commit()

    from app.services.milestones import _ordered_milestones

    rows = _ordered_milestones(db_session, project.id)
    assert [m.id for m in rows] == [h2.id, h1.id]
    assert [m.orden for m in rows] == [1, 2]


def _milestone_create_body(nombre: str, **extra) -> dict:
    body = {
        "record_type": "milestone",
        "titulo": nombre,
        "data": {"tipo": "entrega"},
        "fecha_inicio": "2026-01-01",
        "fecha_fin": "2026-06-30",
    }
    body.update(extra)
    return body


def test_api_create_milestone_ignora_orden_en_body(
    api_client, db_session: Session
):
    from tests.conftest import auth_headers
    from tests.record_helpers import seed_project_with_roles

    project, pm_id, _, _ = seed_project_with_roles(db_session)
    base = f"/api/v1/projects/{project.id}/records"
    headers = auth_headers(pm_id, project.organization_id)

    r1 = api_client.post(
        base,
        json=_milestone_create_body("H1", orden=99),
        headers=headers,
    )
    assert r1.status_code == 201
    assert r1.json()["orden"] == 1

    r2 = api_client.post(
        base,
        json=_milestone_create_body("H2"),
        headers=headers,
    )
    assert r2.status_code == 201
    assert r2.json()["orden"] == 2


def test_api_delete_milestone_recompacta(api_client, db_session: Session):
    from tests.conftest import auth_headers
    from tests.record_helpers import seed_project_with_roles

    project, pm_id, _, _ = seed_project_with_roles(db_session)
    base = f"/api/v1/projects/{project.id}/records"
    headers = auth_headers(pm_id, project.organization_id)

    ids = []
    for name in ("H1", "H2", "H3"):
        r = api_client.post(
            base,
            json=_milestone_create_body(name),
            headers=headers,
        )
        assert r.status_code == 201
        ids.append(r.json()["id"])

    del_r = api_client.delete(f"{base}/{ids[1]}", headers=headers)
    assert del_r.status_code == 204

    list_r = api_client.get(
        f"{base}?record_type=milestone",
        headers=headers,
    )
    assert list_r.status_code == 200
    rows = sorted(list_r.json(), key=lambda r: r["orden"])
    assert [r["titulo"] for r in rows] == ["H1", "H3"]
    assert [r["orden"] for r in rows] == [1, 2]


def test_api_patch_orden_reordena(api_client, db_session: Session):
    from tests.conftest import auth_headers
    from tests.record_helpers import seed_project_with_roles

    project, pm_id, _, _ = seed_project_with_roles(db_session)
    base = f"/api/v1/projects/{project.id}/records"
    headers = auth_headers(pm_id, project.organization_id)

    h1 = api_client.post(
        base, json=_milestone_create_body("H1"), headers=headers
    ).json()
    h2 = api_client.post(
        base, json=_milestone_create_body("H2"), headers=headers
    ).json()
    h3 = api_client.post(
        base, json=_milestone_create_body("H3"), headers=headers
    ).json()

    patch_r = api_client.patch(
        f"{base}/{h3['id']}",
        json={"orden": 1},
        headers=headers,
    )
    assert patch_r.status_code == 200

    list_r = api_client.get(
        f"{base}?record_type=milestone",
        headers=headers,
    )
    rows = sorted(list_r.json(), key=lambda r: r["orden"])
    assert [r["id"] for r in rows] == [h3["id"], h1["id"], h2["id"]]
    assert [r["orden"] for r in rows] == [1, 2, 3]
