"""Tests métricas Scrum (horas)."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Project, ProjectRecord, User
from app.services.scrum_metrics import (
    compute_sprint_completed_horas,
    list_sprint_velocity,
    sum_sprint_committed_horas,
    sync_sprint_horas_completadas,
    sync_sprint_horas_planeadas,
)
from tests.org_helpers import create_organization


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


def test_sync_sprint_horas_completadas(db_session: Session):
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
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )
    )
    sprint = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="sprint",
        titulo="Sprint 1",
        estado="en_progreso",
        created_by=pm_id,
        data={"tipo": "sprint", "horas_planeadas": 40},
    )
    db_session.add(sprint)
    story_done = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="task",
        parent_id=sprint.id,
        titulo="Done",
        estado="completado",
        created_by=pm_id,
        data={"scrum_role": "story"},
    )
    story_open = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="task",
        parent_id=sprint.id,
        titulo="Open",
        estado="en_progreso",
        created_by=pm_id,
        data={"scrum_role": "story"},
    )
    db_session.add_all([story_done, story_open])
    db_session.add(
        ProjectRecord(
            id=uuid4(),
            project_id=project_id,
            record_type="task",
            titulo="T1",
            estado="completed",
            created_by=pm_id,
            data={"scrum_role": "dev", "parent_task_id": str(story_done.id), "estimacion_horas": 5},
        )
    )
    db_session.add(
        ProjectRecord(
            id=uuid4(),
            project_id=project_id,
            record_type="task",
            titulo="T2",
            estado="to_do",
            created_by=pm_id,
            data={"scrum_role": "dev", "parent_task_id": str(story_open.id), "estimacion_horas": 8},
        )
    )
    db_session.commit()

    total = sync_sprint_horas_completadas(db_session, sprint, commit=True)
    assert total == 5.0
    assert sprint.data["horas_completadas"] == 5.0
    assert compute_sprint_completed_horas(db_session, project_id, sprint.id) == 5.0


def test_sync_sprint_horas_planeadas(db_session: Session):
    pm_id = uuid4()
    project_id = uuid4()
    org = create_organization(db_session, owner_id=pm_id)
    db_session.add(
        User(
            id=pm_id,
            email="pm2@test.local",
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
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )
    )
    sprint = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="sprint",
        titulo="Sprint 1",
        estado="en_progreso",
        created_by=pm_id,
        data={"tipo": "sprint", "horas_planeadas": 99},
    )
    story = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="task",
        parent_id=sprint.id,
        titulo="Story",
        estado="pendiente",
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
            estado="to_do",
            created_by=pm_id,
            data={"scrum_role": "dev", "parent_task_id": str(story.id), "estimacion_horas": 12},
        )
    )
    db_session.commit()

    total = sync_sprint_horas_planeadas(db_session, sprint, commit=True)
    assert total == 12.0
    assert sprint.data["horas_planeadas"] == 12.0
    assert sum_sprint_committed_horas(db_session, project_id, sprint.id) == 12.0


def test_list_sprint_velocity_predictibilidad(db_session: Session):
    pm_id = uuid4()
    project_id = uuid4()
    org = create_organization(db_session, owner_id=pm_id)
    db_session.add(
        User(
            id=pm_id,
            email="pm3@test.local",
            nombre="PM",
            password_hash="x",
        )
    )
    db_session.add(
        Project(
            id=project_id,
            nombre="Scrum Test Velocity",
            estado="activo",
            created_by=pm_id,
            organization_id=org.id,
            template_slug="t6_scrum_interno",
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )
    )
    sprint = ProjectRecord(
        id=uuid4(),
        project_id=project_id,
        record_type="sprint",
        titulo="Sprint 1",
        estado="completado",
        created_by=pm_id,
        data={
            "tipo": "sprint",
            "sprint_goal": "Entregar checkout",
            "horas_planeadas": 40,
            "horas_completadas": 32,
        },
    )
    db_session.add(sprint)
    db_session.commit()

    rows = list_sprint_velocity(db_session, project_id, limit=6)
    assert len(rows) == 1
    assert rows[0]["predictibilidad_pct"] == 80.0
    assert rows[0]["sprint_goal"] == "Entregar checkout"
