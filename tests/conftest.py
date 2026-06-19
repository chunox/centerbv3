"""Fixtures compartidos para tests de API con JWT."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.auth_tokens import create_access_token


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


@pytest.fixture
def api_client(db_session: Session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def auth_headers(user_id: UUID, org_id: UUID | None = None) -> dict[str, str]:
    token = create_access_token(user_id=user_id, organization_id=org_id)
    return {"Authorization": f"Bearer {token}"}


def client_auth(user_id: UUID, org_id: UUID | None = None) -> dict[str, str]:
    """Alias for auth_headers used in API tests."""
    return auth_headers(user_id, org_id)
