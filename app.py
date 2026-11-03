"""Local read-only demo for Linux server monitoring."""

import hmac
import os
import secrets
from datetime import timedelta

from flask import (
    Flask,
    abort,
    has_request_context,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.sessions import SecureCookieSessionInterface
from werkzeug.security import check_password_hash, generate_password_hash

ADMIN_USERNAME = "admin"
LOGIN_ERROR = "Invalid username or password."
# Burn a comparable amount of time when no real hash is configured.
_DUMMY_PASSWORD_HASH = generate_password_hash("unused-dummy-password")


def create_app() -> Flask:
    secret = os.environ.get("SECRET_KEY", "")
    if not secret.strip():
        raise RuntimeError(
            "SECRET_KEY is required. Set it in the environment before starting."
        )

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secret,
        ADMIN_PASSWORD_HASH=os.environ.get("ADMIN_PASSWORD_HASH", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
        PERMANENT_SESSION_LIFETIME=_idle_lifetime(),
        SESSION_REFRESH_EACH_REQUEST=True,
    )
    app.session_interface = LocalSessionInterface()

    @app.context_processor
    def inject_csrf():
        return {"csrf_token": ensure_csrf_token}

    @app.before_request
    def require_login():
        if _is_public_request():
            return None
        if session.get("logged_in") is True:
            session.permanent = True
            return None
        return redirect(url_for("login"))

    @app.get("/")
    def fleet():
        return render_template("fleet.html", servers=[])

    @app.get("/servers/<server_id>")
    def server_detail(server_id: str):
        return render_template("server_detail.html", server_id=server_id)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET" and session.get("logged_in") is True:
            return redirect(url_for("fleet"))
        error = None
        if request.method == "POST":
            if not csrf_is_valid():
                abort(400)
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            stored_hash = app.config["ADMIN_PASSWORD_HASH"]
            if credentials_ok(stored_hash, username, password):
                session.clear()
                session["logged_in"] = True
                session["csrf_token"] = secrets.token_urlsafe(32)
                session.permanent = True
                return redirect(url_for("fleet"))
            error = LOGIN_ERROR
        return render_template("login.html", error=error)

    @app.post("/logout")
    def logout():
        if not csrf_is_valid():
            abort(400)
        session.clear()
        return redirect(url_for("login"))

    return app


def credentials_ok(stored_hash: str, username: str, password: str) -> bool:
    """True only for the admin user and a matching hash. Never records the password."""
    presented = password if isinstance(password, str) else ""
    if stored_hash:
        try:
            hash_ok = check_password_hash(stored_hash, presented)
        except (TypeError, ValueError):
            hash_ok = False
    else:
        check_password_hash(_DUMMY_PASSWORD_HASH, presented)
        hash_ok = False
    return username == ADMIN_USERNAME and hash_ok


def ensure_csrf_token() -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_is_valid() -> bool:
    expected = session.get("csrf_token")
    sent = request.form.get("csrf_token", "")
    if not isinstance(expected, str) or not expected or not isinstance(sent, str):
        return False
    return hmac.compare_digest(expected, sent)


def _is_public_request() -> bool:
    if request.endpoint in {"login", "static"}:
        return True
    return request.path.startswith("/static/")


def _idle_lifetime() -> timedelta:
    raw = os.environ.get("SESSION_IDLE_HOURS", "8")
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        hours = 8
    if hours <= 0:
        hours = 8
    return timedelta(hours=hours)


def _is_plain_local_http(scheme: str, host: str) -> bool:
    if scheme != "http":
        return False
    hostname = host.strip().lower()
    if hostname.startswith("["):
        end = hostname.find("]")
        hostname = hostname[1:end] if end != -1 else hostname
    else:
        hostname = hostname.split(":")[0]
    return hostname in {"127.0.0.1", "localhost", "::1"}


class LocalSessionInterface(SecureCookieSessionInterface):
    """Mark the session cookie Secure except on plain local HTTP."""

    def get_cookie_secure(self, app: Flask) -> bool:
        if has_request_context():
            return not _is_plain_local_http(request.scheme, request.host)
        return False


def bind_settings() -> tuple[str, int, bool]:
    """Listen on localhost unless HOST/PORT override it. Debug only if FLASK_DEBUG=1."""
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    return host, port, debug


def main() -> None:
    try:
        application = create_app()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    host, port, debug = bind_settings()
    application.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
