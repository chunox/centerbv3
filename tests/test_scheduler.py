"""Tests scheduler milestone sync (§4.4)."""

from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import Base
from app.models.entities import Feature, Milestone, Project, ProjectMember, User
from app.scheduler import run_scheduled_milestone_sync, shutdown_scheduler, start_scheduler
from tests.org_helpers import add_member_with_slug, create_organization


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
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="P",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2025, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    add_member_with_slug(session, project, pm_id, 'pm')
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2020, 1, 1),
        fecha_fin=date(2020, 6, 1),
        estado="completado",
        created_by=pm_id,
    )
    session.add(milestone)
    session.add(
        Feature(
            id=uuid4(),
            milestone_id=milestone.id,
            project_id=project.id,
            nombre="Hotfix",
            tipo="bug",
            estado="en_progreso",
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 3, 31),
            created_by=pm_id,
        )
    )
    session.commit()
    milestone_id = milestone.id
    session.close()

    monkeypatch.setattr(settings, "milestone_sync_actor_user_id", pm_id)
    monkeypatch.setattr("app.scheduler.SessionLocal", SessionLocal)

    updated = run_scheduled_milestone_sync()
    assert updated == 1

    verify = SessionLocal()
    ms = verify.get(Milestone, milestone_id)
    assert ms is not None
    assert ms.estado == "cerrado_con_bug"
    verify.close()


def test_start_scheduler_deshabilitado_por_defecto(monkeypatch):
    monkeypatch.setattr(settings, "milestone_sync_enabled", False)
    shutdown_scheduler()
    assert start_scheduler() is None
