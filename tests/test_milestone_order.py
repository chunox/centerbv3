"""Orden de hitos: crear al final, recompactar al borrar, reordenar por PATCH."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Milestone, Project, ProjectMember, User
from app.schemas.milestones import MilestoneUpdate
from app.services.deletions import delete_milestone
from app.services.milestones import (
    compact_milestone_ordenes,
    next_milestone_orden,
    reorder_milestone,
    update_milestone,
)
from tests.org_helpers import add_member_with_slug, create_organization


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
    pm_id = uuid4()
    session.add(User(id=pm_id, nombre="PM", email="pm@order.test", password_hash="x"))
    org = create_organization(session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="Proyecto",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    add_member_with_slug(session, project, pm_id, 'pm')
    session.commit()
    return project, pm_id


def _add_milestone(session: Session, project: Project, pm_id, nombre: str, orden: int) -> Milestone:
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre=nombre,
        tipo="entrega",
        orden=orden,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        estado="pendiente",
        created_by=pm_id,
    )
    session.add(milestone)
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
    assert [m.nombre for m in rows] == ["H1", "H3"]
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
