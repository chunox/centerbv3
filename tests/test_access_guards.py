"""Tests guards de acceso alineados con INTERACCIONES_APP (§4, §14)."""

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.entities import User
from app.services.features import apply_feature_action, ensure_default_task
from app.services.records.repository import create_record, list_children
from tests.conftest import auth_headers
from tests.org_helpers import add_member_with_slug, create_organization, create_project_for_org
from tests.record_helpers import (
    create_feature_record,
    create_milestone_record,
    create_query_record,
    seed_project_with_roles,
)


def _seed_interno_blocked(session: Session):
    project, pm_id, dev_id, qa_id = seed_project_with_roles(session)
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_record(
        session,
        project,
        entity_type="feature",
        titulo="Login",
        created_by=pm_id,
        parent_id=milestone.id,
        estado="uat",
        data={"tipo": "desarrollo", "prioridad": "media", "bloqueada": True},
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
    )
    ensure_default_task(session, feature, created_by=pm_id)
    task = list_children(session, feature.id, "task")[0]
    task.estado = "ready_for_test"
    create_query_record(
        session,
        project,
        feature,
        created_by=dev_id,
        titulo="Consulta",
        descripcion="Bloqueo",
        estado="esperando_pm",
    )
    session.commit()
    return project, milestone, feature, pm_id, dev_id, qa_id


def test_bloqueada_impide_enviar_al_pm(db_session: Session):
    project, _, feature, _, _, qa_id = _seed_interno_blocked(db_session)
    with pytest.raises(HTTPException) as exc:
        apply_feature_action(
            db_session,
            feature,
            project,
            action="enviar_al_pm",
            actor_user_id=qa_id,
        )
    assert exc.value.status_code == 409


def test_bloqueada_permite_cancelar(db_session: Session):
    project, _, feature, pm_id, _, _ = _seed_interno_blocked(db_session)
    apply_feature_action(
        db_session,
        feature,
        project,
        action="cancelar",
        actor_user_id=pm_id,
    )
    assert feature.estado == "cancelado"


def test_create_milestone_en_proyecto_cerrado_falla(
    db_session: Session, api_client: TestClient
):
    pm_id = uuid4()
    db_session.add(
        User(id=pm_id, nombre="PM", email="pm@closed.test", password_hash="x")
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(
        db_session, pm_id, org, nombre="Cerrado", estado="cerrado"
    )
    db_session.commit()

    response = api_client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "milestone",
            "titulo": "H2",
            "data": {"tipo": "entrega"},
            "orden": 2,
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-12-31",
        },
        headers=auth_headers(pm_id, org.id),
    )
    assert response.status_code == 409


def test_create_feature_sin_rol_pm_falla(db_session: Session, api_client: TestClient):
    pm_id = uuid4()
    dev_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@feat.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@feat.test", password_hash="x"),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org, nombre="P")
    add_member_with_slug(db_session, project, dev_id, "dev")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    db_session.commit()

    response = api_client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "feature",
            "titulo": "Nueva",
            "parent_id": str(milestone.id),
            "data": {"tipo": "desarrollo", "prioridad": "media", "bloqueada": False},
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-03-31",
        },
        headers=auth_headers(dev_id),
    )
    assert response.status_code == 403


def test_reporte_solo_cliente(db_session: Session, api_client: TestClient):
    pm_id = uuid4()
    cliente_id = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@rep2.test", password_hash="x"),
            User(
                id=cliente_id,
                nombre="Cli",
                email="cli@rep2.test",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(
        db_session, pm_id, org, nombre="CC", tipo="con_cliente"
    )
    add_member_with_slug(db_session, project, cliente_id, "cliente")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_record(
        db_session,
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
    db_session.commit()

    pm_report = api_client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "report",
            "titulo": "Reporte bug",
            "parent_id": str(feature.id),
            "descripcion": "PM no puede",
            "data": {"tipo": "bug", "reported_by": str(pm_id)},
        },
        headers=auth_headers(pm_id, org.id),
    )
    assert pm_report.status_code == 403

    ok = api_client.post(
        f"/api/v1/projects/{project.id}/records",
        json={
            "record_type": "report",
            "titulo": "Reporte bug",
            "parent_id": str(feature.id),
            "descripcion": "Cliente sí",
            "data": {"tipo": "bug", "reported_by": str(cliente_id)},
        },
        headers=auth_headers(cliente_id),
    )
    assert ok.status_code == 201


def test_adjunto_patch_solo_autor_o_pm(db_session: Session, api_client: TestClient):
    pm_id = uuid4()
    dev_id = uuid4()
    other_dev = uuid4()
    db_session.add_all(
        [
            User(id=pm_id, nombre="PM", email="pm@att.test", password_hash="x"),
            User(id=dev_id, nombre="Dev", email="dev@att.test", password_hash="x"),
            User(
                id=other_dev,
                nombre="Dev2",
                email="dev2@att.test",
                password_hash="x",
            ),
        ]
    )
    org = create_organization(db_session, owner_id=pm_id)
    project = create_project_for_org(db_session, pm_id, org, nombre="P")
    add_member_with_slug(db_session, project, dev_id, "dev")
    add_member_with_slug(db_session, project, other_dev, "dev")
    milestone = create_milestone_record(db_session, project, created_by=pm_id)
    feature = create_feature_record(
        db_session,
        project,
        milestone,
        created_by=pm_id,
        with_default_task=False,
    )
    db_session.commit()

    created = api_client.post(
        "/api/v1/attachments",
        json={
            "url": "https://example.com/a.pdf",
            "nombre_original": "a.pdf",
            "mime_type": "application/pdf",
            "tamano_bytes": 10,
            "entidad_tipo": "feature",
            "entidad_id": str(feature.id),
        },
        headers=auth_headers(dev_id),
    )
    assert created.status_code == 201
    att_id = created.json()["id"]
    att_body = created.json()
    db_session.commit()

    forbidden = api_client.patch(
        f"/api/v1/attachments/{att_id}",
        json={"nombre_original": "hack.pdf"},
        headers=auth_headers(other_dev),
    )
    assert forbidden.status_code == 403

    allowed = api_client.patch(
        f"/api/v1/attachments/{att_id}",
        json={
            "nombre_original": "renombrado.pdf",
            "url": att_body["url"],
            "mime_type": att_body["mime_type"],
        },
        headers=auth_headers(pm_id, org.id),
    )
    assert allowed.status_code == 200
    assert allowed.json()["nombre_original"] == "renombrado.pdf"
