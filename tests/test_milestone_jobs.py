"""Tests job sync milestone bug plazos (§4.4)."""

from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.entities import User
from app.services.milestones import sync_all_milestone_states
from app.services.records.repository import create_record
from tests.org_helpers import create_organization, create_project_for_org
from tests.record_helpers import create_milestone_record


def test_bug_fuera_de_plazo_marca_cerrado_con_bug():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    pm_id = uuid4()
    session.add(
        User(id=pm_id, nombre="PM", email="pm@job.test", password_hash="x")
    )
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(
        session,
        pm_id,
        org,
        fecha_inicio=date(2025, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )
    milestone = create_milestone_record(session, project, created_by=pm_id)
    milestone.estado = "completado"
    milestone.fecha_inicio = date(2020, 1, 1)
    milestone.fecha_fin = date(2020, 6, 1)
    create_record(
        session,
        project,
        entity_type="feature",
        titulo="Hotfix",
        created_by=pm_id,
        parent_id=milestone.id,
        estado="en_progreso",
        data={"tipo": "bug", "prioridad": "media", "bloqueada": False},
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
    )
    session.commit()

    sync_all_milestone_states(session, actor_user_id=pm_id, project_id=project.id)
    assert milestone.estado == "cerrado_con_bug"
    session.close()
