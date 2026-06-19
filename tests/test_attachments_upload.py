"""Tests upload binario de adjuntos (§4.11)."""

from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.entities import User
from tests.conftest import auth_headers
from tests.org_helpers import create_organization, create_project_for_org
from tests.record_helpers import create_feature_record, create_milestone_record


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(session: Session):
    pm_id = uuid4()
    session.add(
        User(id=pm_id, nombre="PM", email="pm@up.test", password_hash="x")
    )
    org = create_organization(session, owner_id=pm_id)
    project = create_project_for_org(session, pm_id, org, nombre="P")
    milestone = create_milestone_record(session, project, created_by=pm_id)
    feature = create_feature_record(
        session,
        project,
        milestone,
        created_by=pm_id,
        with_default_task=False,
    )
    session.commit()
    return feature, pm_id, org


def test_upload_y_descarga(monkeypatch, tmp_path: Path):
    session = _session()
    feature, pm_id, org = _seed(session)
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/attachments/upload",
            data={
                "entidad_tipo": "feature",
                "entidad_id": str(feature.id),
            },
            files={"file": ("evidencia.txt", b"hola handoff", "text/plain")},
            headers=auth_headers(pm_id, org.id),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["nombre_original"] == "evidencia.txt"
        assert body["tamano_bytes"] == 12
        assert body["url"].endswith("/file")

        download = client.get(
            f"/api/v1/attachments/{body['id']}/file",
            headers=auth_headers(pm_id, org.id),
        )
        assert download.status_code == 200
        assert download.content == b"hola handoff"
    app.dependency_overrides.clear()
    session.close()


def test_upload_archivo_vacio_falla(monkeypatch, tmp_path: Path):
    session = _session()
    feature, pm_id, org = _seed(session)
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/attachments/upload",
            data={
                "entidad_tipo": "feature",
                "entidad_id": str(feature.id),
            },
            files={"file": ("vacio.txt", b"", "text/plain")},
            headers=auth_headers(pm_id, org.id),
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()
    session.close()


def test_url_externa_no_descarga_local():
    session = _session()
    feature, pm_id, org = _seed(session)

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/attachments",
            json={
                "url": "https://example.com/doc.pdf",
                "nombre_original": "doc.pdf",
                "mime_type": "application/pdf",
                "tamano_bytes": 100,
                "entidad_tipo": "feature",
                "entidad_id": str(feature.id),
            },
            headers=auth_headers(pm_id, org.id),
        )
        assert created.status_code == 201
        att_id = created.json()["id"]

        download = client.get(
            f"/api/v1/attachments/{att_id}/file",
            headers=auth_headers(pm_id, org.id),
        )
        assert download.status_code == 404
    app.dependency_overrides.clear()
    session.close()


def test_patch_url_externa(monkeypatch, tmp_path: Path):
    session = _session()
    feature, pm_id, org = _seed(session)
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/attachments",
            json={
                "url": "https://example.com/old.pdf",
                "nombre_original": "old.pdf",
                "mime_type": "application/pdf",
                "tamano_bytes": 100,
                "entidad_tipo": "feature",
                "entidad_id": str(feature.id),
            },
            headers=auth_headers(pm_id, org.id),
        )
        assert created.status_code == 201
        att_id = created.json()["id"]
        session.commit()
        response = client.patch(
            f"/api/v1/attachments/{att_id}",
            json={
                "url": "https://example.com/new.pdf",
                "nombre_original": "new.pdf",
                "mime_type": "application/pdf",
            },
            headers=auth_headers(pm_id, org.id),
        )
        assert response.status_code == 200
        assert response.json()["url"] == "https://example.com/new.pdf"
        assert response.json()["nombre_original"] == "new.pdf"
    app.dependency_overrides.clear()
    session.close()


def test_patch_url_en_upload_falla(monkeypatch, tmp_path: Path):
    session = _session()
    feature, pm_id, org = _seed(session)
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/attachments/upload",
            data={
                "entidad_tipo": "feature",
                "entidad_id": str(feature.id),
            },
            files={"file": ("doc.txt", b"data", "text/plain")},
            headers=auth_headers(pm_id, org.id),
        )
        att_id = created.json()["id"]
        response = client.patch(
            f"/api/v1/attachments/{att_id}",
            json={"url": "https://example.com/hack.pdf"},
            headers=auth_headers(pm_id, org.id),
        )
        assert response.status_code == 409
    app.dependency_overrides.clear()
    session.close()


def test_delete_adjunto_y_archivo(monkeypatch, tmp_path: Path):
    session = _session()
    feature, pm_id, org = _seed(session)
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/attachments/upload",
            data={
                "entidad_tipo": "feature",
                "entidad_id": str(feature.id),
            },
            files={"file": ("borrar.txt", b"x", "text/plain")},
            headers=auth_headers(pm_id, org.id),
        )
        att_id = created.json()["id"]
        response = client.delete(
            f"/api/v1/attachments/{att_id}",
            headers=auth_headers(pm_id, org.id),
        )
        assert response.status_code == 204
        assert (
            client.get(
                f"/api/v1/attachments/{att_id}",
                headers=auth_headers(pm_id, org.id),
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/attachments/{att_id}/file",
                headers=auth_headers(pm_id, org.id),
            ).status_code
            == 404
        )
        assert not (tmp_path / str(att_id)).exists()
    app.dependency_overrides.clear()
    session.close()
