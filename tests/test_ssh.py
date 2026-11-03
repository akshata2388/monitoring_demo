"""SSH helper tests. The client is a stub, so nothing dials a real host."""

import logging
import socket
from pathlib import Path

import paramiko
import pytest

import collector
import db
import sshutil
from tests.conftest import csrf_token
from tests.fakes import ScriptedClient


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("network socket opened")

    monkeypatch.setattr(socket, "socket", explode)


def test_sources_reject_auto_add_and_eval():
    root = Path(__file__).resolve().parents[1]
    for name in (
        "sshutil.py",
        "collector.py",
        "poller.py",
        "app.py",
        "present.py",
        "db.py",
    ):
        text = (root / name).read_text(encoding="utf-8")
        assert "AutoAddPolicy" not in text
        assert "eval(" not in text
        assert "shell=True" not in text


def test_missing_key_does_not_open_a_client(monkeypatch):
    monkeypatch.delenv("SSH_KEY_PATH", raising=False)

    def factory():
        raise AssertionError("client created")

    with pytest.raises(sshutil.SSHConfigError):
        sshutil.connect("example.invalid", 22, "monitor", client_factory=factory)


def test_connect_uses_reject_policy_and_closes_on_failure(monkeypatch, tmp_path):
    key = _write_key(monkeypatch, tmp_path)
    created = []

    class FakeClient:
        def __init__(self):
            created.append(self)
            self.policy = None
            self.closed = False
            self.kwargs = None
            self.system = False
            self.hosts = None

        def load_system_host_keys(self):
            self.system = True

        def load_host_keys(self, filename):
            self.hosts = filename

        def set_missing_host_key_policy(self, policy):
            self.policy = policy

        def connect(self, **kwargs):
            self.kwargs = kwargs
            raise TimeoutError("banner-do-not-leak")

        def close(self):
            self.closed = True

    with pytest.raises(TimeoutError):
        sshutil.connect(
            "example.invalid",
            22,
            "monitor",
            client_factory=FakeClient,
        )
    client = created[0]
    assert isinstance(client.policy, paramiko.RejectPolicy)
    assert client.system is True
    assert client.closed is True
    assert client.kwargs["password"] is None
    assert client.kwargs["look_for_keys"] is False
    assert client.kwargs["allow_agent"] is False
    assert client.kwargs["key_filename"] == str(key)
    assert client.kwargs["timeout"] == sshutil.CONNECT_TIMEOUT


def test_session_closes_the_client():
    client = ScriptedClient({"true": [(0, "")]})

    def opener(host, port, user):
        assert host == "example.invalid"
        assert port == 22
        assert user == "monitor"
        return client

    with sshutil.session("example.invalid", 22, "monitor", opener=opener):
        assert client.closed is False
    assert client.closed is True


def test_session_closes_when_the_body_fails():
    client = ScriptedClient({})

    def opener(_host, _port, _user):
        return client

    with pytest.raises(TimeoutError):
        with sshutil.session("example.invalid", 22, "monitor", opener=opener):
            raise TimeoutError("timed out")
    assert client.closed is True


def test_failure_kinds():
    assert sshutil.failure_kind(TimeoutError("banner")) == "timeout"
    assert sshutil.failure_kind(paramiko.AuthenticationException("secret")) == "auth"
    assert sshutil.failure_kind(sshutil.SSHConfigError()) == "config"


def test_route_success_timeout_and_auth(logged_in, monkeypatch, tmp_path, caplog):
    _write_key(monkeypatch, tmp_path)
    caplog.set_level(logging.INFO)

    monkeypatch.setattr(sshutil, "connect", lambda *_args, **_kwargs: _noop_client())
    success = _post(logged_in, _fields())
    assert success.status_code == 200
    assert "Connection succeeded. The host was not saved." in success.get_data(as_text=True)
    assert db.list_servers() == []

    def timeout(*_args, **_kwargs):
        raise TimeoutError("banner-do-not-leak")

    monkeypatch.setattr(sshutil, "connect", timeout)
    timed = _post(logged_in, _fields())
    assert "Could not connect." in timed.get_data(as_text=True)
    assert "banner-do-not-leak" not in timed.get_data(as_text=True)
    assert "banner-do-not-leak" not in caplog.text
    assert "kind=timeout" in caplog.text
    assert db.list_servers() == []

    def auth(*_args, **_kwargs):
        raise paramiko.AuthenticationException("auth-secret")

    monkeypatch.setattr(sshutil, "connect", auth)
    denied = _post(logged_in, _fields())
    assert "Could not connect." in denied.get_data(as_text=True)
    assert "auth-secret" not in denied.get_data(as_text=True)
    assert "auth-secret" not in caplog.text
    assert "kind=auth" in caplog.text


def test_route_reports_a_missing_key(logged_in, monkeypatch, caplog):
    caplog.set_level(logging.WARNING)

    def explode(*_args, **_kwargs):
        raise AssertionError("connect called")

    monkeypatch.setattr(sshutil, "connect", explode)
    response = _post(logged_in, _fields())
    assert sshutil.SSH_NOT_CONFIGURED in response.get_data(as_text=True)
    assert "kind=config" in caplog.text
    assert db.list_servers() == []


def test_test_connection_runs_only_true(monkeypatch, tmp_path):
    _write_key(monkeypatch, tmp_path)
    client = _noop_client()
    monkeypatch.setattr(sshutil, "connect", lambda *_args, **_kwargs: client)
    collector.test_connection("example.invalid", 22, "monitor")
    assert client.commands == ["true"]
    assert client.closed is True


def _noop_client():
    return ScriptedClient({"true": [(0, "")]})


def _write_key(monkeypatch, tmp_path):
    path = tmp_path / "demo_key"
    path.write_text("not-a-real-key\n", encoding="utf-8")
    monkeypatch.setenv("SSH_KEY_PATH", str(path))
    return path


def _fields():
    return {"name": "edge", "host": "example.invalid", "ssh_port": "22", "ssh_user": "monitor"}


def _post(client, fields):
    payload = {"csrf_token": csrf_token(client)}
    payload.update(fields)
    return client.post("/admin/servers/test", data=payload)
