"""Tests burndown Scrum — audit de historias completadas (G-01)."""
from datetime import date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.scrum import get_sprint_burndown
from app.database import Base
from app.models.entities import AuditLog, Project, ProjectRecord, User
from app.services.audit import record_audit_log
from app.services.packs import seed_project_from_pack
from tests.org_helpers import add_member_with_slug, create_organization


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


def test_burndown_counts_story_completion_audit(db_session: Session):
    pm_id = uuid4()
    project_id = uuid4()
    org = create_organization(db_session, owner_id=pm_id)
    db_session.add(
        User(
            id=pm_id,
            email="pm@test.local",
            nombre="PM",
            password_hash="x",
        )
    )
    db_session.add(
        Project(
            id=project_id,
            nombre="Scrum Test",
            estado="activo",
            created_by=pm_id,
            organization_id=org.id,
            template_slug="t6_scrum_interno",
            pack_slug="software",
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )
    )
    db_session.flush()
    project = db_session.get(Project, project_id)
    seed_project_from_pack(db_session, project, "software", template_slug="t6_scrum_interno")
    add_member_with_slug(db_session, project, pm_id, "pm")
    sprint = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="milestone",
        titulo="Sprint 1",
        estado="en_progreso",
        created_by=pm_id,
        fecha_inicio=date(2026, 6, 10),
        fecha_fin=date(2026, 6, 17),
        data={"tipo": "sprint"},
    )
    story = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="task",
        parent_id=sprint.id,
        titulo="Historia",
        estado="completado",
        created_by=pm_id,
        data={"scrum_role": "story"},
    )
    db_session.add_all([sprint, story])
    db_session.add(
        ProjectRecord(
            id=uuid4(),
            project_id=project_id,
            record_type="task",
            titulo="Dev",
            estado="completed",
            created_by=pm_id,
            data={"scrum_role": "dev", "parent_task_id": str(story.id), "estimacion_horas": 8},
        )
    )
    db_session.flush()
    record_audit_log(
        db_session,
        project_id=project_id,
        user_id=pm_id,
        entidad_tipo="tarea",
        entidad_id=story.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior="en_progreso",
        valor_nuevo="completado (completar)",
    )
    audit_row = db_session.scalars(select(AuditLog)).first()
    assert audit_row is not None
    audit_row.created_at = datetime(2026, 6, 12, 10, 0, 0)
    db_session.commit()

    result = get_sprint_burndown(
        project_id=project_id,
        sprint_id=sprint.id,
        actor_user_id=pm_id,
        db=db_session,
    )
    assert result["total_horas"] == 8.0
    assert result["completed_horas"] == 8.0
    june_12 = next(d for d in result["days"] if d["date"] == "2026-06-12")
    assert june_12["actual"] == 0.0
