"""Auth tests. The secret and password here are fake and local to this file."""

import os

import pytest
from werkzeug.security import generate_password_hash

from app import LOGIN_ERROR, create_app, main

FAKE_SECRET = "test-secret"
FAKE_PASSWORD = "test-password"
FAKE_HASH = generate_password_hash(FAKE_PASSWORD)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", FAKE_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", FAKE_HASH)
    monkeypatch.delenv("SESSION_IDLE_HOURS", raising=False)
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


def _csrf(client) -> str:
    response = client.get("/login")
    assert response.status_code == 200
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    assert isinstance(token, str) and token
    return token


def _login(client, username="admin", password=FAKE_PASSWORD, token=None):
    if token is None:
        token = _csrf(client)
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
    )


def test_missing_secret_refuses_to_start(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_main_exits_when_secret_missing(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(SystemExit, match="SECRET_KEY"):
        main()


def test_wrong_password_is_rejected(client):
    response = _login(client, password="wrong-password")
    assert response.status_code == 200
    assert LOGIN_ERROR in response.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert sess.get("logged_in") is not True


def test_wrong_username_uses_the_same_error(client):
    wrong_user = _login(client, username="root", password=FAKE_PASSWORD)
    other = create_app().test_client()
    wrong_password = _login(other, username="admin", password="wrong-password")
    assert wrong_user.status_code == 200
    assert wrong_password.status_code == 200
    assert LOGIN_ERROR in wrong_user.get_data(as_text=True)
    assert LOGIN_ERROR in wrong_password.get_data(as_text=True)
    assert "root" not in wrong_user.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert sess.get("logged_in") is not True


def test_correct_password_sets_session(client):
    response = _login(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    with client.session_transaction() as sess:
        assert sess.get("logged_in") is True
        assert "password" not in sess
        assert FAKE_PASSWORD not in repr(dict(sess))
        assert set(sess.keys()) <= {"logged_in", "csrf_token", "_permanent"}


def test_password_is_not_logged(client, caplog):
    caplog.set_level(0)
    unique = "plaintext-password-should-not-be-logged"
    _login(client, password=unique)
    assert unique not in caplog.text


def test_anonymous_root_redirects_without_metrics(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    body = response.get_data(as_text=True)
    assert "No servers yet" not in body
    assert "<th" not in body.lower()


def test_anonymous_detail_and_future_routes_redirect(client):
    for path in ("/servers/sample", "/admin/servers", "/api/servers"):
        response = client.get(path)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        body = response.get_data(as_text=True)
        assert "No data yet" not in body
        assert "sample" not in body


def test_static_files_stay_public(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200


def test_logout_clears_session(client):
    _login(client)
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    response = client.post("/logout", data={"csrf_token": token})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert sess.get("logged_in") is not True
    follow = client.get("/")
    assert follow.status_code == 302
    assert follow.headers["Location"].endswith("/login")


def test_logout_get_does_not_clear_session(client):
    _login(client)
    response = client.get("/logout")
    assert response.status_code == 405
    with client.session_transaction() as sess:
        assert sess.get("logged_in") is True


def test_logout_without_csrf_keeps_session(client):
    _login(client)
    response = client.post("/logout", data={"csrf_token": "not-the-token"})
    assert response.status_code == 400
    assert FAKE_PASSWORD not in response.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert sess.get("logged_in") is True


def test_login_without_csrf_is_rejected(client):
    client.get("/login")
    response = client.post(
        "/login",
        data={"username": "admin", "password": FAKE_PASSWORD, "csrf_token": "nope"},
    )
    assert response.status_code == 400
    assert FAKE_PASSWORD not in response.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert sess.get("logged_in") is not True


def test_session_cookie_flags_on_local_http(client):
    response = client.get("/login", base_url="http://127.0.0.1:5000")
    attrs = _cookie_attrs(_session_cookie(response))
    assert attrs["httponly"] == ""
    assert attrs["samesite"] == "Lax"
    assert "secure" not in attrs


def test_session_cookie_is_secure_off_local_http(app):
    https_client = app.test_client()
    https_cookie = _session_cookie(
        https_client.get("/login", base_url="https://127.0.0.1:5000")
    )
    remote_client = app.test_client()
    remote_cookie = _session_cookie(
        remote_client.get("/login", base_url="http://192.0.2.10:5000")
    )
    assert "secure" in _cookie_attrs(https_cookie)
    assert "secure" in _cookie_attrs(remote_cookie)


def test_idle_lifetime_defaults_to_eight_hours(app):
    assert app.permanent_session_lifetime.total_seconds() == 8 * 60 * 60


def test_idle_lifetime_is_configurable(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", FAKE_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", FAKE_HASH)
    monkeypatch.setenv("SESSION_IDLE_HOURS", "2")
    configured = create_app()
    assert configured.permanent_session_lifetime.total_seconds() == 2 * 60 * 60


def _session_cookie(response) -> str:
    cookies = response.headers.getlist("Set-Cookie")
    assert cookies
    return cookies[0]


def _cookie_attrs(header: str) -> dict[str, str]:
    attrs = {}
    for part in header.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        attrs[name.lower()] = value
    return attrs


def test_env_example_has_no_real_secret():
    example = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), ".env.example"
    )
    text = open(example, encoding="utf-8").read()
    assert "SECRET_KEY=" in text
    assert "ADMIN_PASSWORD_HASH=" in text
    assert FAKE_SECRET not in text
    assert FAKE_PASSWORD not in text
    assert "pbkdf2:" not in text
    assert "scrypt:" not in text
