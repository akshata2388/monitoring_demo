"""Parse fixed read-only Linux metric text. Failures return None."""

import re

MAX_INTERFACES = 32
MAX_PORTS = 100
_PROCESS_RE = re.compile(r'users:\(\("([^"]+)"')


def parse_proc_stat(text: str | None) -> dict | None:
    """Cumulative idle and total jiffies from the aggregate `cpu` line."""
    if not text:
        return None
    for line in text.splitlines():
        if not line.startswith("cpu "):
            continue
        numbers = []
        for part in line.split()[1:8]:
            if not part.isdigit():
                return None
            numbers.append(int(part))
        if len(numbers) < 4:
            return None
        idle = numbers[3] + (numbers[4] if len(numbers) > 4 else 0)
        return {"idle": idle, "total": sum(numbers)}
    return None


def cpu_percent(first: dict | None, second: dict | None) -> float | None:
    if not first or not second:
        return None
    total_delta = second["total"] - first["total"]
    idle_delta = second["idle"] - first["idle"]
    if total_delta <= 0 or idle_delta < 0:
        return None
    busy = total_delta - idle_delta
    if busy < 0:
        return None
    return round(busy / total_delta * 100, 1)


def parse_meminfo(text: str | None) -> dict | None:
    """Used and total bytes. Prefers MemAvailable when it is present."""
    if not text:
        return None
    total_kb = _kb(text, "MemTotal")
    if total_kb is None or total_kb <= 0:
        return None
    available_kb = _kb(text, "MemAvailable")
    if available_kb is None:
        free_kb = _kb(text, "MemFree")
        if free_kb is None:
            return None
        available_kb = free_kb + (_kb(text, "Buffers") or 0) + (_kb(text, "Cached") or 0)
    if available_kb < 0:
        return None
    if available_kb > total_kb:
        available_kb = total_kb
    return {
        "used": (total_kb - available_kb) * 1024,
        "total": total_kb * 1024,
    }


def parse_net_dev(text: str | None) -> list[dict] | None:
    if not text:
        return None
    found = []
    saw_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Inter-") or line.startswith("face"):
            saw_table = True
            continue
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        numbers = rest.split()
        if len(numbers) < 9 or not numbers[0].isdigit() or not numbers[8].isdigit():
            continue
        saw_table = True
        found.append(
            {
                "name": name.strip(),
                "rx_bytes": int(numbers[0]),
                "tx_bytes": int(numbers[8]),
            }
        )
        if len(found) >= MAX_INTERFACES:
            break
    if not saw_table:
        return None
    return found


def parse_ss(text: str | None, *, with_process: bool) -> list[dict] | None:
    if not text:
        return None
    lines = text.splitlines()
    if not lines:
        return None
    header = lines[0].lower()
    if "state" not in header and "netid" not in header:
        return None
    rows = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        protocol = parts[0].lower()
        state = parts[1].upper()
        if protocol.startswith("tcp") and state != "LISTEN":
            continue
        if protocol.startswith("udp") and state not in {"UNCONN", "LISTEN"}:
            continue
        if not protocol.startswith("tcp") and not protocol.startswith("udp"):
            continue
        address, port = _split_address(parts[4])
        if port is None:
            continue
        process = None
        if with_process:
            match = _PROCESS_RE.search(line)
            if match:
                process = match.group(1)
        rows.append(
            {
                "protocol": protocol,
                "address": address,
                "port": port,
                "process": process,
            }
        )
        if len(rows) >= MAX_PORTS:
            break
    return rows


def _kb(text: str, key: str) -> int | None:
    prefix = key + ":"
    for line in text.splitlines():
        if not line.startswith(prefix):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return None
    return None


def _split_address(local: str) -> tuple[str, int | None]:
    if local.startswith("["):
        end = local.find("]")
        if end == -1:
            return local, None
        address = local[: end + 1]
        rest = local[end + 1 :]
        if not rest.startswith(":"):
            return address, None
        port_text = rest[1:]
    else:
        address, separator, port_text = local.rpartition(":")
        if not separator:
            return local, None
    if not port_text.isdigit():
        return address, None
    port = int(port_text)
    if port < 0 or port > 65535:
        return address, None
    return address, port
