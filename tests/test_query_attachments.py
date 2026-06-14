"""Adjuntos en consultas (feature_query)."""

from uuid import uuid4

from fastapi.testclient import TestClient
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.entities import User
from tests.org_helpers import create_organization, create_project_for_org
from tests.record_helpers import (
    create_feature_record,
    create_milestone_record,
    create_query_record,
)


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_upload_adjunto_en_consulta(monkeypatch, tmp_path: Path):
    session = _session()
    pm_id = uuid4()
    session.add(User(id=pm_id, nombre="PM", email="pm@qatt.test", password_hash="x"))
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(session, pm_id, org, nombre="P")
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_feature_record(session, project, milestone, created_by=pm_id)
    query = create_query_record(
        session,
        project,
        feature,
        created_by=pm_id,
        titulo="Consulta SSO",
        descripcion="Detalle",
        estado="esperando_pm",
    )
    session.commit()

    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/attachments/upload",
            data={
                "uploaded_by": str(pm_id),
                "entidad_tipo": "feature_query",
                "entidad_id": str(query.id),
            },
            files={"file": ("evidencia.txt", b"log consulta", "text/plain")},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["nombre_original"] == "evidencia.txt"

        listed = client.get(
            "/api/v1/attachments",
            params={
                "entidad_tipo": "feature_query",
                "entidad_id": str(query.id),
                "viewer_user_id": str(pm_id),
            },
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 1
    app.dependency_overrides.clear()
