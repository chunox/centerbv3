"""
Tests de autenticación — registro, login, refresh, session, logout.
"""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_user, auth_headers


# ─── Register ─────────────────────────────────────────────────────────────────

def test_register_creates_user_and_returns_token(client: TestClient):
    res = client.post("/api/v1/auth/register", json={
        "nombre": "Nuevo Usuario",
        "email": "nuevo@test.demo",
        "password": "secure123",
    })
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "nuevo@test.demo"


def test_register_duplicate_email_returns_409(client: TestClient, db):
    make_user(db, email="dup@test.demo")
    db.commit()
    res = client.post("/api/v1/auth/register", json={
        "nombre": "Otro",
        "email": "dup@test.demo",
        "password": "pass1234567",
    })
    assert res.status_code == 409


# ─── Login ────────────────────────────────────────────────────────────────────

def test_login_valid_credentials(client: TestClient, db):
    make_user(db, email="login@test.demo", password="mypass")
    db.commit()
    res = client.post("/api/v1/auth/login", json={
        "email": "login@test.demo",
        "password": "mypass",
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "login@test.demo"


def test_login_wrong_password_returns_401(client: TestClient, db):
    make_user(db, email="bad@test.demo", password="correct")
    db.commit()
    res = client.post("/api/v1/auth/login", json={
        "email": "bad@test.demo",
        "password": "wrong",
    })
    assert res.status_code == 401


def test_login_unknown_email_returns_401(client: TestClient):
    res = client.post("/api/v1/auth/login", json={
        "email": "nobody@test.demo",
        "password": "pass",
    })
    assert res.status_code == 401


# ─── Session ──────────────────────────────────────────────────────────────────

def test_session_with_valid_token(client: TestClient, db):
    user = make_user(db, email="sess@test.demo")
    db.commit()
    res = client.get("/api/v1/auth/session", headers=auth_headers(user))
    assert res.status_code == 200
    assert res.json()["user"]["email"] == "sess@test.demo"


def test_session_without_token_returns_401(client: TestClient):
    res = client.get("/api/v1/auth/session")
    assert res.status_code == 401


# ─── Logout ───────────────────────────────────────────────────────────────────

def test_logout_clears_cookie(client: TestClient, db):
    user = make_user(db, email="logout@test.demo")
    db.commit()
    res = client.post("/api/v1/auth/logout", headers=auth_headers(user))
    assert res.status_code == 200


# ─── Forgot / Reset password stubs ───────────────────────────────────────────

def test_forgot_password_returns_204(client: TestClient):
    res = client.post("/api/v1/auth/forgot-password", json={"email": "any@test.demo"})
    assert res.status_code == 204


def test_reset_password_invalid_token(client: TestClient):
    """Un token inválido/expirado devuelve 400, no 204."""
    res = client.post("/api/v1/auth/reset-password", json={
        "token": "invalid-fake-token",
        "new_password": "newpass123",
    })
    assert res.status_code == 400


# ─── Rate limiting ────────────────────────────────────────────────────────────

def test_login_rate_limit_burst_returns_429(client: TestClient, db):
    make_user(db, email="ratelimit@test.demo", password="mypass")
    db.commit()

    payload = {"email": "ratelimit@test.demo", "password": "wrong"}
    ip_headers = {"X-Forwarded-For": "10.99.0.1"}
    for _ in range(10):
        res = client.post("/api/v1/auth/login", json=payload, headers=ip_headers)
        assert res.status_code == 401

    res = client.post("/api/v1/auth/login", json=payload, headers=ip_headers)
    assert res.status_code == 429
