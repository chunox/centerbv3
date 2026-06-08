"""Tests hilo de comentarios en consultas/reportes."""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base

from app.models.entities import (
    AuditLog,
    Feature,
    FeatureQuery,
    FeatureReport,
    Milestone,
    Notification,
    Project,
    ProjectMember,
    User,
)
from app.services.comments import create_comment
from app.schemas.comments import CommentCreate
from tests.org_helpers import create_organization


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
    session.add_all(
        [
            ProjectMember(project_id=project.id, user_id=pm_id, rol="pm"),
            ProjectMember(
                project_id=project.id, user_id=cliente_id, rol="cliente"
            ),
            ProjectMember(project_id=project.id, user_id=dev_id, rol="dev"),
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
        estado="completado",
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        created_by=pm_id,
    )
    session.add(feature)
    session.commit()
    return project, feature, pm_id, cliente_id, dev_id


def test_comentario_reporte_audit_guarda_parent(db_session: Session):
    project, feature, pm_id, cliente_id, _ = _seed_con_cliente(db_session)
    report = FeatureReport(
        id=uuid4(),
        feature_id=feature.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Botón roto",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    create_comment(
        db_session,
        CommentCreate(
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
    report = FeatureReport(
        id=uuid4(),
        feature_id=feature.id,
        reported_by=cliente_id,
        tipo="bug",
        descripcion="Botón roto",
        estado="pendiente",
    )
    db_session.add(report)
    db_session.commit()

    create_comment(
        db_session,
        CommentCreate(
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
    query = FeatureQuery(
        id=uuid4(),
        feature_id=feature.id,
        titulo="Duda API",
        descripcion="¿Cuál es el endpoint?",
        estado="pendiente_aprobacion_pm",
        created_by=dev_id,
    )
    db_session.add(query)
    db_session.commit()

    create_comment(
        db_session,
        CommentCreate(
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
