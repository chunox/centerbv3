"""Tests del flujo de consultas (§4.8)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Feature, FeatureQuery, Milestone, Project, ProjectMember, User
from app.services.feature_queries import apply_query_action, sync_feature_bloqueada
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


def _seed_con_cliente(session: Session):
    pm_id = uuid4()
    dev_id = uuid4()
    cliente_id = uuid4()
    session.add_all(
        [
            User(
                id=pm_id,
                nombre="PM",
                email="pm@test.com",
                password_hash="x",
            ),
            User(
                id=dev_id,
                nombre="Dev",
                email="dev@test.com",
                password_hash="x",
            ),
            User(
                id=cliente_id,
                nombre="Cliente",
                email="cli@test.com",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="P",
        tipo="con_cliente",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    session.add(project)
    session.add_all(
        [
            ProjectMember(project_id=project.id, user_id=pm_id, rol="pm"),
            ProjectMember(project_id=project.id, user_id=dev_id, rol="dev"),
            ProjectMember(
                project_id=project.id, user_id=cliente_id, rol="cliente"
            ),
        ]
    )
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        created_by=pm_id,
    )
    session.add(milestone)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Login",
        tipo="desarrollo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(feature)
    session.commit()
    return project, feature, pm_id, dev_id, cliente_id


def test_dev_query_flow_blocks_until_closed(db_session: Session):
    project, feature, pm_id, dev_id, cliente_id = _seed_con_cliente(db_session)
    query = FeatureQuery(
        id=uuid4(),
        feature_id=feature.id,
        titulo="¿Color del botón?",
        descripcion="Necesitamos confirmación",
        estado="borrador",
        created_by=dev_id,
    )
    db_session.add(query)
    db_session.commit()

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="solicitar_envio",
        actor_user_id=dev_id,
        actor_rol="dev",
    )
    db_session.flush()
    assert query.estado == "pendiente_aprobacion_pm"
    assert sync_feature_bloqueada(
        db_session, feature, project, actor_user_id=pm_id
    )

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="aprobar_envio",
        actor_user_id=pm_id,
        actor_rol="pm",
    )
    db_session.flush()
    assert query.estado == "esperando_cliente"
    assert feature.bloqueada is True

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="responder",
        actor_user_id=cliente_id,
        actor_rol="cliente",
    )
    assert query.estado == "respuesta_cliente"

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="validar_rechazar",
        actor_user_id=pm_id,
        actor_rol="pm",
    )
    assert query.estado == "esperando_cliente"

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="responder",
        actor_user_id=cliente_id,
        actor_rol="cliente",
    )
    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="validar_aceptar",
        actor_user_id=pm_id,
        actor_rol="pm",
    )
    assert query.estado == "cerrada"
    assert (
        sync_feature_bloqueada(
            db_session, feature, project, actor_user_id=pm_id
        )
        is False
    )


def test_cumulative_blocking_two_queries(db_session: Session):
    project, feature, pm_id, dev_id, _ = _seed_con_cliente(db_session)
    q1 = FeatureQuery(
        id=uuid4(),
        feature_id=feature.id,
        titulo="Q1",
        descripcion="D1",
        estado="esperando_cliente",
        created_by=dev_id,
    )
    q2 = FeatureQuery(
        id=uuid4(),
        feature_id=feature.id,
        titulo="Q2",
        descripcion="D2",
        estado="esperando_cliente",
        created_by=dev_id,
    )
    db_session.add_all([q1, q2])
    db_session.commit()
    sync_feature_bloqueada(db_session, feature, project, actor_user_id=pm_id)
    assert feature.bloqueada is True

    q1.estado = "cerrada"
    db_session.flush()
    sync_feature_bloqueada(db_session, feature, project, actor_user_id=pm_id)
    assert feature.bloqueada is True

    q2.estado = "cerrada"
    db_session.flush()
    sync_feature_bloqueada(db_session, feature, project, actor_user_id=pm_id)
    assert feature.bloqueada is False


def test_interno_pm_self_block(db_session: Session):
    pm_id = uuid4()
    db_session.add(
        User(id=pm_id, nombre="PM", email="pm2@test.com", password_hash="x")
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = Project(
        organization_id=org.id,
        id=uuid4(),
        nombre="Interno",
        tipo="interno",
        estado="activo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        created_by=pm_id,
    )
    db_session.add(project)
    db_session.add(
        ProjectMember(project_id=project.id, user_id=pm_id, rol="pm")
    )
    milestone = Milestone(
        id=uuid4(),
        project_id=project.id,
        nombre="H1",
        tipo="entrega",
        orden=1,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 6, 30),
        created_by=pm_id,
    )
    db_session.add(milestone)
    feature = Feature(
        id=uuid4(),
        milestone_id=milestone.id,
        project_id=project.id,
        nombre="Export",
        tipo="desarrollo",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    db_session.add(feature)
    query = FeatureQuery(
        id=uuid4(),
        feature_id=feature.id,
        titulo="IVA",
        descripcion="Confirmar con cliente externo",
        estado="borrador",
        created_by=pm_id,
    )
    db_session.add(query)
    db_session.commit()

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="activar",
        actor_user_id=pm_id,
        actor_rol="pm",
    )
    assert query.estado == "esperando_pm"
    assert feature.bloqueada is True

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="cerrar",
        actor_user_id=pm_id,
        actor_rol="pm",
    )
    assert query.estado == "cerrada"
    assert feature.bloqueada is False
