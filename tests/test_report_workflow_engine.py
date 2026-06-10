"""Tests del motor de workflow unificado para reportes."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Feature, FeatureReport, Milestone, Notification, Project, User
from app.services.feature_reports import apply_report_action
from app.services.workflow.engine import apply_entity_transition
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


def _seed_con_cliente(session: Session, *, fecha_fin_milestone: date):
    pm_id = uuid4()
    cliente_id = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@wf.test", password_hash="x"),
            User(id=cliente_id, nombre="Cli", email="cli@wf.test", password_hash="x"),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="CC",
        tipo="con_cliente",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    add_member_with_slug(session, project, pm_id, "pm")
    add_member_with_slug(session, project, cliente_id, "cliente")
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=fecha_fin_milestone,
        created_by=pm_id,
    )
    session.add(milestone)
    original = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        estado="completado",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(original)
    session.commit()
    return project, milestone, original, pm_id, cliente_id


def test_apply_entity_transition_rechazar_reporte(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Error",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    apply_entity_transition(
        db_session,
        project,
        report,
        entity_type="report",
        action_id="rechazar",
        actor_user_id=pm_id,
        form_data={"motivo": "No reproducible"},
        side_effect_context={"milestone_id": milestone.id},
    )
    db_session.commit()

    assert report.estado == "rechazado"
    notif = db_session.scalar(
        select(Notification).where(
            Notification.user_id == cliente_id,
            Notification.tipo == "reporte_resuelto",
        )
    )
    assert notif is not None


def test_apply_entity_transition_aprobar_bug_genera_feature(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Botón roto",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    apply_entity_transition(
        db_session,
        project,
        report,
        entity_type="report",
        action_id="aprobar",
        actor_user_id=pm_id,
        form_data={"nombre_feature": "Hotfix login"},
        side_effect_context={"milestone_id": milestone.id},
    )
    db_session.commit()

    assert report.estado == "aprobado"
    generated = db_session.scalar(
        select(Feature).where(Feature.nombre == "Hotfix login")
    )
    assert generated is not None
    assert generated.tipo == "bug"


def test_apply_entity_transition_transicion_invalida(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="X",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        apply_entity_transition(
            db_session,
            project,
            report,
            entity_type="report",
            action_id="aprobar",
            actor_user_id=cliente_id,
            form_data={},
            side_effect_context={"milestone_id": milestone.id},
        )
    assert exc.value.status_code in (403, 422)


def test_apply_report_action_mejora_requiere_form_data(db_session: Session):
    project, milestone, original, pm_id, cliente_id = _seed_con_cliente(
        db_session, fecha_fin_milestone=date(2026, 6, 30)
    )
    report = FeatureReport(
        id=uuid4(),
        feature_id=original.id,
        reported_by=cliente_id,
        tipo="mejora",
        descripcion="Ampliar alcance",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        apply_report_action(
            db_session,
            report,
            original,
            project,
            milestone,
            action="aprobar",
            actor_user_id=pm_id,
        )
    assert exc.value.status_code == 422
