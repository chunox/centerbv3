"""Tests job sync milestone bug plazos (§4.4)."""

from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Feature, Milestone, Project, ProjectMember, User
from app.services.milestones import sync_all_milestone_states
from tests.org_helpers import create_organization


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
    session.add(ProjectMember(project_id=project.id, user_id=pm_id, rol="pm"))
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

    sync_all_milestone_states(session, actor_user_id=pm_id, project_id=project.id)
    assert milestone.estado == "cerrado_con_bug"
    session.close()
