"""Local SQLite inventory and the latest metric snapshot per server.

The database holds no SSH passwords or key material. Snapshot JSON is stored
and loaded with the json module only.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    ssh_port INTEGER NOT NULL,
    ssh_user TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    id INTEGER PRIMARY KEY,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    collected_at TEXT NOT NULL,
    cpu_percent REAL,
    mem_used_bytes INTEGER,
    mem_total_bytes INTEGER,
    network_json TEXT,
    ports_json TEXT,
    error TEXT
);
"""


def database_path() -> str:
    configured = os.environ.get("DATABASE_PATH", "").strip()
    if configured:
        return configured
    return str(Path(__file__).resolve().parent / "monitor.db")


@contextmanager
def connect(path: str | None = None):
    conn = sqlite3.connect(path or database_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: str | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def add_server(
    name: str,
    host: str,
    ssh_port: int,
    ssh_user: str,
    path: str | None = None,
) -> int:
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect(path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO servers (name, host, ssh_port, ssh_user, enabled, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (name, host, ssh_port, ssh_user, created),
        )
        return int(cursor.lastrowid)


def list_servers(path: str | None = None) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute(
            """
            SELECT id, name, host, ssh_port, ssh_user, enabled, created_at
            FROM servers ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_enabled_servers(path: str | None = None) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute(
            """
            SELECT id, name, host, ssh_port, ssh_user, enabled, created_at
            FROM servers WHERE enabled = 1 ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_server(server_id: int, path: str | None = None) -> dict | None:
    with connect(path) as conn:
        row = conn.execute(
            """
            SELECT id, name, host, ssh_port, ssh_user, enabled, created_at
            FROM servers WHERE id = ?
            """,
            (server_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_server(server_id: int, path: str | None = None) -> bool:
    with connect(path) as conn:
        existing = conn.execute(
            "SELECT id FROM servers WHERE id = ?", (server_id,)
        ).fetchone()
        if existing is None:
            return False
        conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        return True


def save_snapshot(
    server_id: int,
    *,
    cpu_percent: float | None,
    mem_used_bytes: int | None,
    mem_total_bytes: int | None,
    network_json: str | None,
    ports_json: str | None,
    error: str | None,
    path: str | None = None,
) -> None:
    """Keep a single latest row per server."""
    collected = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect(path) as conn:
        conn.execute(
            "DELETE FROM metric_snapshots WHERE server_id = ?", (server_id,)
        )
        conn.execute(
            """
            INSERT INTO metric_snapshots (
                server_id, collected_at, cpu_percent, mem_used_bytes,
                mem_total_bytes, network_json, ports_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                server_id,
                collected,
                cpu_percent,
                mem_used_bytes,
                mem_total_bytes,
                network_json,
                ports_json,
                error,
            ),
        )


def latest_snapshot(server_id: int, path: str | None = None) -> dict | None:
    with connect(path) as conn:
        row = conn.execute(
            """
            SELECT id, server_id, collected_at, cpu_percent, mem_used_bytes,
                   mem_total_bytes, network_json, ports_json, error
            FROM metric_snapshots
            WHERE server_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (server_id,),
        ).fetchone()
    return dict(row) if row else None


def snapshot_count(server_id: int, path: str | None = None) -> int:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM metric_snapshots WHERE server_id = ?",
            (server_id,),
        ).fetchone()
    return int(row["n"])
