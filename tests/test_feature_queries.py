"""Tests del flujo de consultas (§4.8)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.entities import Notification, User
from app.services.feature_queries import apply_query_action, sync_feature_bloqueada
from app.services.records.repository import get_field
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org
from tests.record_helpers import (
    create_feature_record,
    create_milestone_record,
    create_query_record,
)


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
    project = create_project_for_org(session, pm_id, org, nombre="P", tipo="con_cliente")
    add_member_with_slug(session, project, dev_id, "dev")
    add_member_with_slug(session, project, cliente_id, "cliente")
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_feature_record(
        session,
        project,
        milestone,
        created_by=pm_id,
        with_default_task=False,
    )
    session.commit()
    return project, feature, pm_id, dev_id, cliente_id


def test_dev_query_flow_blocks_until_closed(db_session: Session):
    project, feature, pm_id, dev_id, cliente_id = _seed_con_cliente(db_session)
    query = create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="¿Color del botón?",
        descripcion="Necesitamos confirmación",
    )
    db_session.commit()

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="solicitar_envio",
        actor_user_id=dev_id,
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
    )
    db_session.flush()
    assert query.estado == "esperando_cliente"
    assert get_field(feature, "bloqueada") is True

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="responder",
        actor_user_id=cliente_id,
    )
    assert query.estado == "respuesta_cliente"

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="validar_rechazar",
        actor_user_id=pm_id,
    )
    assert query.estado == "esperando_cliente"

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="responder",
        actor_user_id=cliente_id,
    )
    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="validar_aceptar",
        actor_user_id=pm_id,
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
    q1 = create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="Q1",
        descripcion="D1",
        estado="esperando_cliente",
    )
    q2 = create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="Q2",
        descripcion="D2",
        estado="esperando_cliente",
    )
    db_session.commit()
    sync_feature_bloqueada(db_session, feature, project, actor_user_id=pm_id)
    assert get_field(feature, "bloqueada") is True

    q1.estado = "cerrada"
    db_session.flush()
    sync_feature_bloqueada(db_session, feature, project, actor_user_id=pm_id)
    assert get_field(feature, "bloqueada") is True

    q2.estado = "cerrada"
    db_session.flush()
    sync_feature_bloqueada(db_session, feature, project, actor_user_id=pm_id)
    assert get_field(feature, "bloqueada") is False


def test_reject_notifies_query_author(db_session: Session):
    project, feature, pm_id, dev_id, _ = _seed_con_cliente(db_session)
    query = create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="Consulta dev",
        descripcion="Detalle",
        estado="esperando_cliente",
    )
    db_session.commit()

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="rechazar",
        actor_user_id=pm_id,
    )
    db_session.flush()
    assert query.estado == "rechazada"

    notif = db_session.scalar(
        select(Notification).where(
            Notification.user_id == dev_id,
            Notification.tipo == "query_rechazada",
            Notification.entidad_id == query.id,
        )
    )
    assert notif is not None


def test_interno_dev_solicitar_skips_pm_approval(db_session: Session):
    pm_id = uuid4()
    dev_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm3@test.com", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev3@test.com", password_hash="x"),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org, nombre="Interno Dev")
    add_member_with_slug(db_session, project, dev_id, "dev")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        nombre="API",
        with_default_task=False,
    )
    query = create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="¿Formato export?",
        descripcion="Confirmar con stakeholder externo",
    )
    db_session.commit()

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="solicitar_envio",
        actor_user_id=dev_id,
    )
    db_session.flush()
    assert query.estado == "esperando_pm"
    assert get_field(feature, "bloqueada") is True

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="cerrar",
        actor_user_id=pm_id,
    )
    assert query.estado == "cerrada"
    assert get_field(feature, "bloqueada") is False


def test_interno_pm_self_block(db_session: Session):
    pm_id = uuid4()
    db_session.add(
        User(id=pm_id, nombre="PM", email="pm2@test.com", password_hash="x")
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org, nombre="Interno")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        nombre="Export",
        with_default_task=False,
    )
    query = create_query_record(
        db_session,
        project,
        feature,
        created_by=pm_id,
        titulo="IVA",
        descripcion="Confirmar con cliente externo",
    )
    db_session.commit()

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="activar",
        actor_user_id=pm_id,
    )
    assert query.estado == "esperando_pm"
    assert get_field(feature, "bloqueada") is True

    apply_query_action(
        db_session,
        query,
        feature,
        project,
        action="cerrar",
        actor_user_id=pm_id,
    )
    assert query.estado == "cerrada"
    assert get_field(feature, "bloqueada") is False
