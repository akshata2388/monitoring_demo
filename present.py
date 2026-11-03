"""Turn stored rows into display text. JSON is parsed as data, never evaluated."""

import json

import sshutil

CPU_WARN_PERCENT = 90
UNAVAILABLE = "metric unavailable"
NO_SAMPLE = "No sample yet."

STATUS_LABELS = {
    "pending": "Waiting",
    "down": "Unreachable",
    "warn": "High CPU",
    "up": "Up",
}
_KNOWN_ERRORS = {sshutil.SSH_NOT_CONFIGURED, sshutil.SSH_FAILED}


def fleet_row(server: dict, snapshot: dict | None) -> dict:
    code = status_code(snapshot)
    if snapshot is None:
        cpu = "—"
        memory = "—"
        checked = "—"
    else:
        cpu = _cpu_text(snapshot)
        memory = _memory_percent_text(snapshot)
        checked = str(snapshot.get("collected_at") or "—")
    return {
        "id": int(server["id"]),
        "name": server["name"],
        "host": server["host"],
        "status": code,
        "status_label": STATUS_LABELS[code],
        "cpu": cpu,
        "memory": memory,
        "checked": checked,
        "error": safe_error(snapshot),
    }


def detail_view(server: dict, snapshot: dict | None) -> dict:
    code = status_code(snapshot)
    network, network_message = _network(snapshot)
    ports, ports_message = _ports(snapshot)
    if snapshot is None:
        cpu = NO_SAMPLE
        memory = NO_SAMPLE
        checked = "—"
    else:
        cpu = _cpu_text(snapshot)
        memory = _memory_detail_text(snapshot)
        checked = str(snapshot.get("collected_at") or "—")
    return {
        "id": int(server["id"]),
        "name": server["name"],
        "host": server["host"],
        "ssh_port": int(server["ssh_port"]),
        "ssh_user": server["ssh_user"],
        "status": code,
        "status_label": STATUS_LABELS[code],
        "error": safe_error(snapshot),
        "checked": checked,
        "cpu": cpu,
        "memory": memory,
        "network": network,
        "network_message": network_message,
        "ports": ports,
        "ports_message": ports_message,
    }


def status_code(snapshot: dict | None) -> str:
    if snapshot is None:
        return "pending"
    if safe_error(snapshot):
        return "down"
    cpu = _number(snapshot.get("cpu_percent"))
    if cpu is not None and cpu >= CPU_WARN_PERCENT:
        return "warn"
    return "up"


def safe_error(snapshot: dict | None) -> str:
    if not snapshot:
        return ""
    error = snapshot.get("error") or ""
    if not isinstance(error, str) or not error:
        return ""
    if error in _KNOWN_ERRORS:
        return error
    return sshutil.SSH_FAILED


def _cpu_text(snapshot: dict) -> str:
    if safe_error(snapshot):
        return UNAVAILABLE
    cpu = _number(snapshot.get("cpu_percent"))
    if cpu is None:
        return UNAVAILABLE
    return f"{cpu:.1f}%"


def _memory_percent_text(snapshot: dict) -> str:
    used, total = _memory_pair(snapshot)
    if used is None or total is None:
        return UNAVAILABLE
    return f"{used / total * 100:.0f}%"


def _memory_detail_text(snapshot: dict) -> str:
    used, total = _memory_pair(snapshot)
    if used is None or total is None:
        return UNAVAILABLE
    percent = used / total * 100
    return f"{percent:.0f}% · {format_bytes(used)} / {format_bytes(total)}"


def _memory_pair(snapshot: dict) -> tuple[int | None, int | None]:
    if safe_error(snapshot):
        return None, None
    used = _whole(snapshot.get("mem_used_bytes"))
    total = _whole(snapshot.get("mem_total_bytes"))
    if used is None or total is None or total <= 0:
        return None, None
    return used, total


def _network(snapshot: dict | None) -> tuple[list[dict], str]:
    if snapshot is None:
        return [], NO_SAMPLE
    if safe_error(snapshot):
        return [], UNAVAILABLE
    parsed = _load_json(snapshot.get("network_json"))
    if not isinstance(parsed, list):
        return [], UNAVAILABLE
    rows = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        if name == "lo":
            continue
        rx = _whole(item.get("rx_bytes"))
        tx = _whole(item.get("tx_bytes"))
        if rx is None or tx is None:
            continue
        rows.append(
            {
                "iface": name,
                "rx": format_bytes(rx),
                "tx": format_bytes(tx),
                "rx_rate": format_rate(_number(item.get("rx_bps"))),
                "tx_rate": format_rate(_number(item.get("tx_bps"))),
            }
        )
    if not rows:
        return [], "No interfaces."
    return rows, ""


def _ports(snapshot: dict | None) -> tuple[list[dict], str]:
    if snapshot is None:
        return [], NO_SAMPLE
    if safe_error(snapshot):
        return [], UNAVAILABLE
    parsed = _load_json(snapshot.get("ports_json"))
    if not isinstance(parsed, list):
        return [], UNAVAILABLE
    rows = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        port = _whole(item.get("port"))
        if port is None:
            continue
        process = item.get("process")
        rows.append(
            {
                "protocol": str(item.get("protocol", "")),
                "address": str(item.get("address", "")),
                "port": str(port),
                "process": "" if process is None else str(process),
            }
        )
    if not rows:
        return [], "No listening ports."
    return rows, ""


def format_bytes(num: int) -> str:
    if num >= 1024**3:
        return f"{num / 1024**3:.1f} GB"
    if num >= 1024**2:
        return f"{num / 1024**2:.0f} MB"
    return f"{num} B"


def format_rate(bps: float | None) -> str:
    if bps is None:
        return "—"
    if bps >= 1024**2:
        return f"{bps / 1024**2:.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.1f} KB/s"
    return f"{bps:.0f} B/s"


def _load_json(text):
    if not isinstance(text, str) or not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _whole(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)
