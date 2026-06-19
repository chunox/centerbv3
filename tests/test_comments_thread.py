"""Tests hilo de comentarios en consultas/reportes."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import AuditLog, Notification, User
from app.schemas.comments import CommentCreate
from app.services.comments import create_comment
from app.services.records.repository import create_record
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org
from tests.record_helpers import create_milestone_record, create_query_record, create_report_record


class CommentCreateWithUser(CommentCreate):
    user_id: UUID


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


def _seed_con_cliente(session: Session):
    pm_id = uuid4()
    cliente_id = uuid4()
    dev_id = uuid4()
    session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@cmt.test", password_hash="x"),
            User(
                id=cliente_id,
                nombre="Cli",
                email="cli@cmt.test",
                password_hash="x",
            ),
            User(id=dev_id, nombre="Dev", email="dev@cmt.test", password_hash="x"),
        ]
    )
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(session, pm_id, org, nombre="CC", tipo="con_cliente")
    add_member_with_slug(session, project, cliente_id, "cliente")
    add_member_with_slug(session, project, dev_id, "dev")
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_record(
        session,
        project,
        entity_type="feature",
        titulo="Login",
        created_by=pm_id,
        parent_id=milestone.id,
        estado="completado",
        data={"tipo": "desarrollo", "prioridad": "media", "bloqueada": False},
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
    )
    session.commit()
    return project, feature, pm_id, cliente_id, dev_id


def test_comentario_reporte_audit_guarda_parent(db_session: Session):
    project, feature, pm_id, cliente_id, _ = _seed_con_cliente(db_session)
    report = create_report_record(
        db_session,
        project,
        feature,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Botón roto",
    )
    db_session.commit()

    create_comment(
        db_session,
        CommentCreateWithUser(
            entidad_tipo="feature_report",
            entidad_id=report.id,
            user_id=pm_id,
            contenido="¿Tenés captura de pantalla?",
        ),
    )
    db_session.commit()

    log = db_session.scalar(
        select(AuditLog).where(
            AuditLog.project_id == project.id,
            AuditLog.entidad_tipo == "comment",
            AuditLog.accion == "created",
        )
    )
    assert log is not None
    assert log.campo == "feature_report"
    assert log.valor_nuevo == str(report.id)


def test_comentario_reporte_notifica_cliente(db_session: Session):
    project, feature, pm_id, cliente_id, _ = _seed_con_cliente(db_session)
    report = create_report_record(
        db_session,
        project,
        feature,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Botón roto",
    )
    db_session.commit()

    create_comment(
        db_session,
        CommentCreateWithUser(
            entidad_tipo="feature_report",
            entidad_id=report.id,
            user_id=pm_id,
            contenido="Revisamos el caso",
        ),
    )
    db_session.commit()

    notif = db_session.scalar(
        select(Notification).where(
            Notification.user_id == cliente_id,
            Notification.tipo == "comentario_nuevo",
            Notification.entidad_id == report.id,
        )
    )
    assert notif is not None


def test_comentario_consulta_notifica_autor(db_session: Session):
    project, feature, pm_id, _, dev_id = _seed_con_cliente(db_session)
    query = create_query_record(
        db_session,
        project,
        feature,
        created_by=dev_id,
        titulo="Duda API",
        descripcion="¿Cuál es el endpoint?",
        estado="pendiente_aprobacion_pm",
    )
    db_session.commit()

    create_comment(
        db_session,
        CommentCreateWithUser(
            entidad_tipo="feature_query",
            entidad_id=query.id,
            user_id=pm_id,
            contenido="Lo vemos con el cliente",
        ),
    )
    db_session.commit()

    notif = db_session.scalar(
        select(Notification).where(
            Notification.user_id == dev_id,
            Notification.tipo == "comentario_nuevo",
            Notification.entidad_id == query.id,
        )
    )
    assert notif is not None
