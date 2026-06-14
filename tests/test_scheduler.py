"""Tests scheduler milestone sync (§4.4)."""

from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models.entities import ProjectRecord, User
from app.scheduler import run_scheduled_milestone_sync, shutdown_scheduler, start_scheduler
from app.services.records.repository import create_record
from tests.org_helpers import create_organization, create_project_for_org
from tests.record_helpers import create_milestone_record


def test_run_scheduled_milestone_sync_sin_actor(monkeypatch):
    monkeypatch.setattr(settings, "milestone_sync_actor_user_id", None)
    assert run_scheduled_milestone_sync() == 0


def test_run_scheduled_milestone_sync_ejecuta_job(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    pm_id = uuid4()
    session.add(
        User(id=pm_id, nombre="PM", email="pm@sched.test", password_hash="x")
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
    milestone_id = milestone.id
    session.close()

    monkeypatch.setattr(settings, "milestone_sync_actor_user_id", pm_id)
    monkeypatch.setattr("app.scheduler.SessionLocal", SessionLocal)

    updated = run_scheduled_milestone_sync()
    assert updated == 1

    verify = SessionLocal()
    ms = verify.get(ProjectRecord, milestone_id)
    assert ms is not None
    assert ms.estado == "cerrado_con_bug"
    verify.close()


def test_start_scheduler_deshabilitado_por_defecto(monkeypatch):
    monkeypatch.setattr(settings, "milestone_sync_enabled", False)
    shutdown_scheduler()
    assert start_scheduler() is None
