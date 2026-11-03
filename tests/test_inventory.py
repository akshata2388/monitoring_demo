"""Inventory tests use a temporary database and do not open sockets."""

import os
import socket
import sqlite3
import subprocess

import pytest

import db
import inventory
from tests.conftest import csrf_token


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("network socket opened")

    monkeypatch.setattr(socket, "socket", explode)


def test_schema_has_no_secrets(app):
    conn = sqlite3.connect(db.database_path())
    servers = {row[1] for row in conn.execute("PRAGMA table_info(servers)")}
    snapshots = {row[1] for row in conn.execute("PRAGMA table_info(metric_snapshots)")}
    conn.close()
    assert servers == {
        "id",
        "name",
        "host",
        "ssh_port",
        "ssh_user",
        "enabled",
        "created_at",
    }
    assert "password" not in servers
    assert snapshots == {
        "id",
        "server_id",
        "collected_at",
        "cpu_percent",
        "mem_used_bytes",
        "mem_total_bytes",
        "network_json",
        "ports_json",
        "error",
    }


def test_add_list_and_delete(logged_in):
    created = _post(
        logged_in,
        "/admin/servers",
        {"name": "edge", "host": "192.0.2.10", "ssh_port": "", "ssh_user": "monitor"},
    )
    assert created.status_code == 302
    page = logged_in.get("/admin/servers")
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "edge" in body
    assert "192.0.2.10" in body
    assert "monitor" in body
    assert "Server added." in body
    rows = db.list_servers()
    assert len(rows) == 1
    assert rows[0]["ssh_port"] == 22
    assert rows[0]["enabled"] == 1

    removed = _post(logged_in, f"/admin/servers/{rows[0]['id']}/delete", {})
    assert removed.status_code == 302
    assert db.list_servers() == []
    after = logged_in.get("/admin/servers")
    assert "Server removed." in after.get_data(as_text=True)
    assert "edge" not in after.get_data(as_text=True)


def test_invalid_port_is_rejected(logged_in):
    response = _post(
        logged_in,
        "/admin/servers",
        {"name": "edge", "host": "192.0.2.10", "ssh_port": "70000", "ssh_user": "monitor"},
    )
    assert response.status_code == 400
    assert "Port must be between 1 and 65535." in response.get_data(as_text=True)
    assert db.list_servers() == []


def test_shell_metacharacters_are_rejected(logged_in, monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("subprocess started")

    monkeypatch.setattr(subprocess, "Popen", explode)
    monkeypatch.setattr(os, "system", explode)
    response = _post(
        logged_in,
        "/admin/servers",
        {
            "name": "edge",
            "host": "192.0.2.10;id",
            "ssh_port": "22",
            "ssh_user": "root;id",
        },
    )
    assert response.status_code == 400
    assert db.list_servers() == []


def test_unexpected_field_is_rejected(logged_in):
    response = _post(
        logged_in,
        "/admin/servers",
        {
            "name": "edge",
            "host": "192.0.2.10",
            "ssh_port": "22",
            "ssh_user": "monitor",
            "password": "should-not-be-stored",
        },
    )
    assert response.status_code == 400
    assert "Unexpected fields." in response.get_data(as_text=True)
    assert "should-not-be-stored" not in response.get_data(as_text=True)
    assert db.list_servers() == []
    assert "should-not-be-stored" not in open(db.database_path(), "rb").read().decode(
        "utf-8", "replace"
    )


def test_delete_missing_server_is_404(logged_in):
    kept = db.add_server("keep", "192.0.2.20", 22, "monitor")
    missing = _post(logged_in, "/admin/servers/999/delete", {})
    assert missing.status_code == 404
    assert "999" not in missing.get_data(as_text=True)
    assert db.get_server(kept)["name"] == "keep"


def test_delete_get_is_rejected(logged_in):
    server_id = db.add_server("keep", "192.0.2.20", 22, "monitor")
    response = logged_in.get(f"/admin/servers/{server_id}/delete")
    assert response.status_code == 405
    assert db.get_server(server_id) is not None


def test_add_requires_csrf(logged_in):
    response = logged_in.post(
        "/admin/servers",
        data={"name": "edge", "host": "192.0.2.10", "ssh_port": "22", "ssh_user": "monitor"},
    )
    assert response.status_code == 400
    assert db.list_servers() == []


def test_anonymous_admin_redirects(client):
    response = client.get("/admin/servers")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert "192.0.2.10" not in response.get_data(as_text=True)


def test_user_charset_helper():
    with pytest.raises(inventory.FormError):
        inventory.parse_server_form(
            {"name": "edge", "host": "192.0.2.10", "ssh_port": "22", "ssh_user": "bad user"},
            require_name=True,
        )


def _post(client, path, fields):
    payload = {"csrf_token": csrf_token(client)}
    payload.update(fields)
    return client.post(path, data=payload)
