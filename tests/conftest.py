"""Shared fixtures. The secret and password here are fake."""

import pytest
from werkzeug.security import generate_password_hash

import collector
from app import create_app

FAKE_PASSWORD = "test-password"
FAKE_HASH = generate_password_hash(FAKE_PASSWORD)


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "monitor.db"))
    monkeypatch.delenv("SSH_KEY_PATH", raising=False)
    monkeypatch.delenv("SSH_KNOWN_HOSTS", raising=False)
    collector.reset_state()
    yield
    collector.reset_state()


@pytest.fixture
def app(isolated_database, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", FAKE_HASH)
    monkeypatch.delenv("SESSION_IDLE_HOURS", raising=False)
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


def csrf_token(client) -> str:
    with client.session_transaction() as sess:
        token = sess.get("csrf_token")
    assert isinstance(token, str) and token
    return token


@pytest.fixture
def logged_in(client):
    client.get("/login")
    response = client.post(
        "/login",
        data={
            "username": "admin",
            "password": FAKE_PASSWORD,
            "csrf_token": csrf_token(client),
        },
    )
    assert response.status_code == 302
    return client
