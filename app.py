"""Local read-only demo for Linux server monitoring."""

import hmac
import logging
import os
import secrets
import sys
from datetime import timedelta

from flask import (
    Flask,
    abort,
    flash,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.sessions import SecureCookieSessionInterface
from werkzeug.security import check_password_hash, generate_password_hash

import collector
import db
import inventory
import poller
import present
import sshutil

ADMIN_USERNAME = "admin"
LOGIN_ERROR = "Invalid username or password."
# Burn a comparable amount of time when no real hash is configured.
_DUMMY_PASSWORD_HASH = generate_password_hash("unused-dummy-password")
logger = logging.getLogger(__name__)


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
    db.init_db()

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
        return render_template("fleet.html", servers=_fleet_rows())

    @app.get("/servers/<int:server_id>")
    def server_detail(server_id: int):
        payload = _detail_payload(server_id)
        if payload is None:
            abort(404)
        return render_template("server_detail.html", server=payload)

    @app.get("/admin/servers")
    def admin_servers():
        return _render_admin()

    @app.post("/admin/servers")
    def add_server():
        if not csrf_is_valid():
            abort(400)
        try:
            fields = inventory.parse_server_form(request.form, require_name=True)
        except inventory.FormError as exc:
            return _render_admin(error=exc.message, form=request.form), 400
        db.add_server(
            fields["name"], fields["host"], fields["ssh_port"], fields["ssh_user"]
        )
        flash("Server added.")
        return redirect(url_for("admin_servers"))

    @app.post("/admin/servers/test")
    def test_server():
        if not csrf_is_valid():
            abort(400)
        try:
            fields = inventory.parse_server_form(request.form, require_name=False)
        except inventory.FormError as exc:
            return _render_admin(error=exc.message, form=request.form), 400
        notice, error = _test_ssh(fields)
        return _render_admin(notice=notice, error=error, form=fields)

    @app.post("/admin/servers/<int:server_id>/delete")
    def delete_server(server_id: int):
        if not csrf_is_valid():
            abort(400)
        try:
            inventory.reject_unexpected(request.form, inventory.DELETE_FIELDS)
        except inventory.FormError:
            abort(400)
        if db.get_server(server_id) is None:
            abort(404)
        db.delete_server(server_id)
        collector.clear_server(server_id)
        flash("Server removed.")
        return redirect(url_for("admin_servers"))

    @app.get("/api/servers")
    def api_servers():
        return jsonify({"servers": _fleet_rows()})

    @app.get("/api/servers/<int:server_id>/metrics")
    def api_server_metrics(server_id: int):
        payload = _detail_payload(server_id)
        if payload is None:
            return jsonify({"error": "Not found"}), 404
        return jsonify(payload)

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

    @app.errorhandler(404)
    def not_found(_exc):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return render_template("error.html"), 404

    return app


def _fleet_rows() -> list[dict]:
    rows = []
    for server in db.list_servers():
        rows.append(present.fleet_row(server, db.latest_snapshot(int(server["id"]))))
    return rows


def _detail_payload(server_id: int) -> dict | None:
    server = db.get_server(server_id)
    if server is None:
        return None
    return present.detail_view(server, db.latest_snapshot(server_id))


def _render_admin(error=None, notice=None, form=None):
    return render_template(
        "admin_servers.html",
        servers=db.list_servers(),
        error=error,
        notice=notice,
        form=form or {},
    )


def _test_ssh(fields: dict) -> tuple[str | None, str | None]:
    """Return a fixed notice or a generic error. Details stay in the log."""
    if sshutil.key_path() is None:
        logger.warning("ssh test failed kind=config")
        return None, sshutil.SSH_NOT_CONFIGURED
    try:
        collector.test_connection(fields["host"], fields["ssh_port"], fields["ssh_user"])
    except Exception as exc:
        logger.warning("ssh test failed kind=%s", sshutil.failure_kind(exc))
        return None, sshutil.SSH_FAILED
    return "Connection succeeded. The host was not saved.", None


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


def configure_logging() -> None:
    """Stdout only. Paramiko is kept at WARNING so key material is not logged."""
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(handler, logging.StreamHandler) for handler in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root.addHandler(handler)


def main() -> None:
    try:
        application = create_app()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    configure_logging()
    poller.start_poller()
    host, port, debug = bind_settings()
    application.run(
        host=host,
        port=port,
        debug=debug,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
