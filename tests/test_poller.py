"""Poller tests use the SSH stub. They do not open sockets or dial a host."""

import logging
import socket
from pathlib import Path

import pytest

import db
import poller
import sshutil
from tests.fakes import ScriptedClient

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("network socket opened")

    monkeypatch.setattr(socket, "socket", explode)


def test_poll_writes_one_snapshot(app, caplog):
    caplog.set_level(logging.INFO)
    server_id = db.add_server("edge", "192.0.2.10", 22, "monitor")
    client = _client()

    def opener(_host, _port, _user):
        return client

    poller.poll_once(opener=opener, sleeper=lambda _seconds: None)
    poller.poll_once(opener=opener, sleeper=lambda _seconds: None)
    assert db.snapshot_count(server_id) == 1
    row = db.latest_snapshot(server_id)
    assert row["error"] is None
    assert row["cpu_percent"] == 50.0
    assert row["mem_used_bytes"] == 4000000 * 1024
    assert "eth0" in row["network_json"]
    assert "sshd" in row["ports_json"]
    assert client.closed is True
    assert "poll start" in caplog.text
    assert "poll duration" in caplog.text
    assert "UNIQUE_METRIC_OUTPUT" not in caplog.text


def test_one_failure_does_not_stop_the_other_host(app, caplog):
    caplog.set_level(logging.INFO)
    down_id = db.add_server("down", "down.example", 22, "monitor")
    up_id = db.add_server("up", "192.0.2.10", 22, "monitor")

    def opener(host, _port, _user):
        if host == "down.example":
            raise TimeoutError("LEAKED_BANNER")
        return _client()

    poller.poll_once(opener=opener, sleeper=lambda _seconds: None)
    failed = db.latest_snapshot(down_id)
    healthy = db.latest_snapshot(up_id)
    assert failed["error"] == sshutil.SSH_FAILED
    assert failed["cpu_percent"] is None
    assert "LEAKED_BANNER" not in (failed["error"] or "")
    assert healthy["error"] is None
    assert healthy["cpu_percent"] == 50.0
    assert "kind=timeout" in caplog.text
    assert "LEAKED_BANNER" not in caplog.text
    assert "UNIQUE_METRIC_OUTPUT" not in caplog.text


def test_missing_key_is_a_stored_error_without_connecting(app, monkeypatch):
    monkeypatch.delenv("SSH_KEY_PATH", raising=False)
    server_id = db.add_server("edge", "192.0.2.10", 22, "monitor")

    def explode(*_args, **_kwargs):
        raise AssertionError("connect called")

    monkeypatch.setattr(sshutil, "connect", explode)
    poller.poll_once(sleeper=lambda _seconds: None)
    row = db.latest_snapshot(server_id)
    assert row["error"] == sshutil.SSH_NOT_CONFIGURED


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _client():
    memory = _text("meminfo.txt") + "\nUNIQUE_METRIC_OUTPUT\n"
    return ScriptedClient(
        {
            "cat /proc/stat": [
                (0, _text("proc_stat_a.txt")),
                (0, _text("proc_stat_b.txt")),
                (0, _text("proc_stat_a.txt")),
                (0, _text("proc_stat_b.txt")),
            ],
            "cat /proc/meminfo": [(0, memory)],
            "cat /proc/net/dev": [(0, _text("net_dev.txt"))],
            "ss -tulnp": [(0, _text("ss_tulnp.txt"))],
            "ss -tuln": [(0, _text("ss_tuln.txt"))],
        }
    )
