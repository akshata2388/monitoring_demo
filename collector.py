"""Run the fixed command list over an open SSH client and parse metrics."""

import logging
import socket
import time

import sshutil
from metrics import cpu_percent, parse_meminfo, parse_net_dev, parse_proc_stat, parse_ss

logger = logging.getLogger(__name__)

CPU_COMMAND = "cat /proc/stat"
MEM_COMMAND = "cat /proc/meminfo"
NET_COMMAND = "cat /proc/net/dev"
PORTS_COMMAND = "ss -tuln"
PORTS_PROCESS_COMMAND = "ss -tulnp"
NOOP_COMMAND = "true"
ALLOWED_COMMANDS = frozenset(
    {
        CPU_COMMAND,
        MEM_COMMAND,
        NET_COMMAND,
        PORTS_COMMAND,
        PORTS_PROCESS_COMMAND,
        NOOP_COMMAND,
    }
)
EXEC_TIMEOUT = 5.0
MAX_OUTPUT = 65536
SAMPLE_GAP_SECONDS = 0.2

# Previous interface counters, keyed by server id, so a later poll can show a rate.
_previous_net: dict[int, tuple[float, dict[str, tuple[int, int]]]] = {}


def reset_state() -> None:
    _previous_net.clear()


def clear_server(server_id: int) -> None:
    _previous_net.pop(server_id, None)


def run_command(client, command: str, timeout: float = EXEC_TIMEOUT) -> tuple[int, str]:
    if command not in ALLOWED_COMMANDS:
        raise RuntimeError("command not allow-listed")
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    try:
        stdout.channel.settimeout(timeout)
        # Stderr is discarded so a full remote transcript is never logged.
        output = stdout.read(MAX_OUTPUT)
        stderr.read(MAX_OUTPUT)
        code = stdout.channel.recv_exit_status()
        return code, output.decode("utf-8", "replace")
    finally:
        for stream in (stdin, stdout, stderr):
            try:
                stream.close()
            except Exception:
                pass


def test_connection(host: str, port: int, user: str) -> None:
    """Connect and run the constant command `true`. Raises on failure."""
    with sshutil.session(host, port, user) as client:
        code, _output = run_command(client, NOOP_COMMAND)
        if code != 0:
            raise ConnectionError("noop failed")


def collect_from_client(client, server_id: int, sleeper=time.sleep, clock=time.monotonic) -> dict:
    """Parse each metric independently. A bad sample becomes None, not an exception."""
    first = _read(client, CPU_COMMAND)
    sleeper(SAMPLE_GAP_SECONDS)
    second = _read(client, CPU_COMMAND)
    cpu = None
    if first is not None and second is not None:
        cpu = cpu_percent(parse_proc_stat(first), parse_proc_stat(second))

    memory_text = _read(client, MEM_COMMAND)
    memory = parse_meminfo(memory_text) if memory_text is not None else None

    network_text = _read(client, NET_COMMAND)
    network = parse_net_dev(network_text) if network_text is not None else None
    if network is not None:
        network = _with_rates(server_id, network, clock())

    return {
        "cpu_percent": cpu,
        "mem_used_bytes": None if memory is None else memory["used"],
        "mem_total_bytes": None if memory is None else memory["total"],
        "network": network,
        "ports": _read_ports(client),
    }


def _read(client, command: str) -> str | None:
    try:
        code, output = run_command(client, command)
    except (TimeoutError, socket.timeout, OSError):
        logger.warning("metric command failed command=%s", command)
        return None
    if code != 0:
        return None
    return output


def _read_ports(client) -> list | None:
    probed = _read(client, PORTS_PROCESS_COMMAND)
    if probed is not None:
        parsed = parse_ss(probed, with_process=True)
        if parsed is not None:
            return parsed
    plain = _read(client, PORTS_COMMAND)
    if plain is None:
        return None
    return parse_ss(plain, with_process=False)


def _with_rates(server_id: int, interfaces: list[dict], now: float) -> list[dict]:
    current = {
        item["name"]: (item["rx_bytes"], item["tx_bytes"]) for item in interfaces
    }
    previous = _previous_net.get(server_id)
    _previous_net[server_id] = (now, current)
    if previous is None:
        return interfaces
    previous_time, previous_map = previous
    elapsed = now - previous_time
    if elapsed <= 0:
        return interfaces
    for item in interfaces:
        old = previous_map.get(item["name"])
        if old is None:
            continue
        rx_delta = item["rx_bytes"] - old[0]
        tx_delta = item["tx_bytes"] - old[1]
        if rx_delta < 0 or tx_delta < 0:
            continue
        item["rx_bps"] = rx_delta / elapsed
        item["tx_bps"] = tx_delta / elapsed
    return interfaces
