"""Collector tests drive a stub client. They do not open sockets."""

import socket
from pathlib import Path

import pytest

import collector
from tests.fakes import ScriptedClient

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("network socket opened")

    monkeypatch.setattr(socket, "socket", explode)


def test_commands_are_a_fixed_allow_list():
    client = ScriptedClient({})
    with pytest.raises(RuntimeError, match="allow-listed"):
        collector.run_command(client, "rm -rf /")
    assert client.commands == []
    assert collector.ALLOWED_COMMANDS == {
        "cat /proc/stat",
        "cat /proc/meminfo",
        "cat /proc/net/dev",
        "ss -tuln",
        "ss -tulnp",
        "true",
    }


def test_collects_metrics_and_a_rate_from_the_previous_sample():
    client = _client(net_samples=_net_pair())
    clocks = iter([100.0, 110.0])
    first = collector.collect_from_client(
        client, 7, sleeper=lambda _seconds: None, clock=lambda: next(clocks)
    )
    second = collector.collect_from_client(
        client, 7, sleeper=lambda _seconds: None, clock=lambda: next(clocks)
    )
    assert first["cpu_percent"] == 50.0
    assert first["mem_used_bytes"] == 4000000 * 1024
    assert first["mem_total_bytes"] == 8000000 * 1024
    eth0 = next(item for item in first["network"] if item["name"] == "eth0")
    assert "rx_bps" not in eth0
    eth0_later = next(item for item in second["network"] if item["name"] == "eth0")
    assert eth0_later["rx_bps"] == 400
    assert eth0_later["tx_bps"] == 200
    assert first["ports"][0]["process"] == "sshd"
    assert "ss -tuln" not in client.commands


def test_ports_fall_back_when_process_listing_fails():
    client = _client(ports_code=1)
    payload = collector.collect_from_client(client, 3, sleeper=lambda _seconds: None)
    assert payload["ports"][0]["process"] is None
    assert payload["ports"][0]["port"] == 68
    assert "ss -tuln" in client.commands


def test_bad_cpu_sample_does_not_drop_memory():
    text = _text("proc_stat_bad.txt")
    client = _client(cpu_samples=[(0, text), (0, text)])
    payload = collector.collect_from_client(client, 4, sleeper=lambda _seconds: None)
    assert payload["cpu_percent"] is None
    assert payload["mem_total_bytes"] == 8000000 * 1024


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _net_pair():
    first = _text("net_dev.txt")
    second = first.replace("eth0: 1000", "eth0: 5000").replace(
        "eth0: 5000 1 0 0 0 0 0 0 2000",
        "eth0: 5000 1 0 0 0 0 0 0 4000",
    )
    return [(0, first), (0, second)]


def _client(net_samples=None, ports_code=0, cpu_samples=None):
    cpu = cpu_samples or [
        (0, _text("proc_stat_a.txt")),
        (0, _text("proc_stat_b.txt")),
    ]
    ports = _text("ss_tulnp.txt") if ports_code == 0 else "permission denied\n"
    return ScriptedClient(
        {
            "cat /proc/stat": cpu,
            "cat /proc/meminfo": [(0, _text("meminfo.txt"))],
            "cat /proc/net/dev": net_samples or [(0, _text("net_dev.txt"))],
            "ss -tulnp": [(ports_code, ports)],
            "ss -tuln": [(0, _text("ss_tuln.txt"))],
        }
    )
