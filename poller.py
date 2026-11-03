"""Poll enabled servers one at a time and store the latest snapshot.

A failure on one host is logged and stored, then the loop continues.
"""

import json
import logging
import os
import threading
import time

import collector
import db
import sshutil

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15.0


def interval_seconds() -> float:
    raw = os.environ.get("POLL_INTERVAL_SECONDS", "").strip()
    if not raw:
        return POLL_INTERVAL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return POLL_INTERVAL_SECONDS
    if value <= 0:
        return POLL_INTERVAL_SECONDS
    return value


def poll_once(opener=None, sleeper=time.sleep) -> None:
    for server in db.list_enabled_servers():
        _poll_server(server, opener=opener, sleeper=sleeper)


def poll_loop(stop: threading.Event) -> None:
    wait = interval_seconds()
    while not stop.is_set():
        try:
            poll_once()
        except Exception as exc:
            logger.warning("poll loop kind=%s", exc.__class__.__name__)
        stop.wait(wait)


def start_poller() -> threading.Event:
    stop = threading.Event()
    thread = threading.Thread(target=poll_loop, args=(stop,), name="poller", daemon=True)
    thread.start()
    return stop


def _poll_server(server: dict, opener, sleeper) -> None:
    server_id = int(server["id"])
    logger.info("poll start server_id=%s", server_id)
    started = time.perf_counter()
    error = None
    payload = _empty_payload()
    try:
        if opener is None and sshutil.key_path() is None:
            error = sshutil.SSH_NOT_CONFIGURED
            logger.warning("ssh failure server_id=%s kind=config", server_id)
        else:
            with sshutil.session(
                server["host"], int(server["ssh_port"]), server["ssh_user"], opener=opener
            ) as client:
                payload = collector.collect_from_client(
                    client, server_id, sleeper=sleeper
                )
    except Exception as exc:
        logger.warning(
            "ssh failure server_id=%s kind=%s",
            server_id,
            sshutil.failure_kind(exc),
        )
        error = (
            sshutil.SSH_NOT_CONFIGURED
            if isinstance(exc, sshutil.SSHConfigError)
            else sshutil.SSH_FAILED
        )
        payload = _empty_payload()
    logger.info(
        "poll duration server_id=%s seconds=%.3f",
        server_id,
        time.perf_counter() - started,
    )
    db.save_snapshot(
        server_id,
        cpu_percent=payload["cpu_percent"],
        mem_used_bytes=payload["mem_used_bytes"],
        mem_total_bytes=payload["mem_total_bytes"],
        network_json=_dump(payload["network"]),
        ports_json=_dump(payload["ports"]),
        error=error,
    )


def _empty_payload() -> dict:
    return {
        "cpu_percent": None,
        "mem_used_bytes": None,
        "mem_total_bytes": None,
        "network": None,
        "ports": None,
    }


def _dump(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"))
