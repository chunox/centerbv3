from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import PasswordResetToken, User
from app.security import hash_password, verify_password


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


def test_forgot_y_reset_password(db_session: Session, api_client: TestClient):
    user_id = uuid4()
    email = "reset-me@test.local"
    old_password = "oldpass123"
    new_password = "newpass456"
    db_session.add(
        User(
            id=user_id,
            nombre="Reset User",
            email=email,
            password_hash=hash_password(old_password),
        )
    )
    db_session.commit()

    response = api_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": email},
    )
    assert response.status_code == 200
    assert "registrado" in response.json()["message"].lower()

    token_row = db_session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
    )
    assert token_row is not None

    response = api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token_row.token, "password": new_password},
    )
    assert response.status_code == 200

    db_session.refresh(token_row)
    assert token_row.used_at is not None

    user = db_session.get(User, user_id)
    assert user is not None
    assert verify_password(new_password, user.password_hash)
    assert not verify_password(old_password, user.password_hash)

    response = api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token_row.token, "password": "another123"},
    )
    assert response.status_code == 400


def test_forgot_password_email_desconocido(api_client: TestClient):
    response = api_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nobody@example.test"},
    )
    assert response.status_code == 200


def test_reset_password_token_expirado(db_session: Session, api_client: TestClient):
    user_id = uuid4()
    db_session.add(
        User(
            id=user_id,
            nombre="Expired",
            email="expired@test.local",
            password_hash=hash_password("pass12345"),
        )
    )
    db_session.flush()
    row = PasswordResetToken(
        user_id=user_id,
        token="expired-token-value-32chars-min",
        expires_at=datetime.utcnow() - timedelta(hours=1),
    )
    db_session.add(row)
    db_session.commit()

    response = api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": row.token, "password": "newpass789"},
    )
    assert response.status_code == 410
