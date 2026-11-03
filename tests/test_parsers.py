"""Parser tests read fixture files only. No hostnames, keys, or customer data."""

from pathlib import Path

from metrics import (
    MAX_INTERFACES,
    cpu_percent,
    parse_meminfo,
    parse_net_dev,
    parse_proc_stat,
    parse_ss,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_cpu_percent_from_two_samples():
    first = parse_proc_stat(_text("proc_stat_a.txt"))
    second = parse_proc_stat(_text("proc_stat_b.txt"))
    assert first == {"idle": 800, "total": 1000}
    assert cpu_percent(first, second) == 50.0


def test_cpu_bad_sample_is_unavailable():
    assert parse_proc_stat(_text("proc_stat_bad.txt")) is None
    assert cpu_percent(None, {"idle": 1, "total": 2}) is None


def test_memory_uses_available_and_bytes():
    parsed = parse_meminfo(_text("meminfo.txt"))
    assert parsed == {"used": 4000000 * 1024, "total": 8000000 * 1024}


def test_memory_falls_back_without_available():
    parsed = parse_meminfo(_text("meminfo_fallback.txt"))
    assert parsed == {"used": 800 * 1024, "total": 1000 * 1024}


def test_memory_bad_sample_is_unavailable():
    assert parse_meminfo(_text("meminfo_bad.txt")) is None


def test_network_counters_and_bad_sample():
    parsed = parse_net_dev(_text("net_dev.txt"))
    assert parsed == [
        {"name": "lo", "rx_bytes": 100, "tx_bytes": 200},
        {"name": "eth0", "rx_bytes": 1000, "tx_bytes": 2000},
    ]
    assert parse_net_dev(_text("net_dev_bad.txt")) is None


def test_network_caps_interfaces():
    lines = ["Inter-| Receive | Transmit", " face |bytes"]
    for index in range(MAX_INTERFACES + 5):
        lines.append(f"eth{index}: {index} 0 0 0 0 0 0 0 {index} 0 0 0 0 0 0 0")
    parsed = parse_net_dev("\n".join(lines))
    assert len(parsed) == MAX_INTERFACES


def test_listening_ports_and_process_name():
    plain = parse_ss(_text("ss_tuln.txt"), with_process=False)
    assert plain == [
        {"protocol": "udp", "address": "0.0.0.0", "port": 68, "process": None},
        {"protocol": "tcp", "address": "127.0.0.1", "port": 22, "process": None},
        {"protocol": "tcp", "address": "[::]", "port": 443, "process": None},
    ]
    with_process = parse_ss(_text("ss_tulnp.txt"), with_process=True)
    assert with_process[0]["process"] == "sshd"
    assert with_process[0]["port"] == 22
    assert with_process[1]["process"] is None


def test_ports_bad_sample_is_unavailable():
    assert parse_ss(_text("ss_bad.txt"), with_process=False) is None
