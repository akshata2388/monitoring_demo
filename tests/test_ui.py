"""UI tests use the Flask client and fixture snapshots. No browser and no SSH."""

import json
from pathlib import Path

import db
import present
import sshutil

GB = 1024**3


def test_fleet_and_detail_render_snapshots(logged_in):
    healthy = db.add_server("<b>web</b>", "192.0.2.10", 22, "monitor")
    partial = db.add_server("partial", "192.0.2.11", 22, "monitor")
    down = db.add_server("down", "192.0.2.12", 22, "monitor")
    db.save_snapshot(
        healthy,
        cpu_percent=12.5,
        mem_used_bytes=GB,
        mem_total_bytes=2 * GB,
        network_json=json.dumps(
            [
                {"name": "lo", "rx_bytes": 10, "tx_bytes": 10},
                {
                    "name": "eth0",
                    "rx_bytes": 1048576,
                    "tx_bytes": 2097152,
                    "rx_bps": 1024,
                    "tx_bps": 2048,
                },
            ]
        ),
        ports_json=json.dumps(
            [
                {
                    "protocol": "tcp",
                    "address": "127.0.0.1",
                    "port": 22,
                    "process": "sshd",
                }
            ]
        ),
        error=None,
    )
    db.save_snapshot(
        partial,
        cpu_percent=None,
        mem_used_bytes=GB,
        mem_total_bytes=2 * GB,
        network_json=None,
        ports_json=json.dumps(
            [{"protocol": "tcp", "address": "127.0.0.1", "port": 80, "process": None}]
        ),
        error=None,
    )
    db.save_snapshot(
        down,
        cpu_percent=None,
        mem_used_bytes=None,
        mem_total_bytes=None,
        network_json=None,
        ports_json=None,
        error="Traceback banner secret",
    )

    fleet = logged_in.get("/")
    body = fleet.get_data(as_text=True)
    assert fleet.status_code == 200
    assert "&lt;b&gt;web&lt;/b&gt;" in body
    assert "<b>web</b>" not in body
    assert "12.5%" in body
    assert "status-up" in body
    assert "50%" in body
    assert "metric unavailable" in body
    assert "Could not connect." in body
    assert "banner secret" not in body
    assert "status-down" in body
    assert body.lower().count("<form") == 1

    detail = logged_in.get(f"/servers/{healthy}")
    detail_body = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert "1.0 GB / 2.0 GB" in detail_body
    assert "eth0" in detail_body
    assert "1.0 KB/s" in detail_body
    assert ">lo<" not in detail_body
    assert "sshd" in detail_body
    assert "127.0.0.1" in detail_body
    assert detail_body.lower().count("<form") == 1

    missing_cpu = logged_in.get(f"/servers/{partial}")
    partial_body = missing_cpu.get_data(as_text=True)
    assert "metric unavailable" in partial_body
    assert "1.0 GB / 2.0 GB" in partial_body
    assert ">80<" in partial_body


def test_high_cpu_is_amber(logged_in):
    assert present.CPU_WARN_PERCENT == 90
    server_id = db.add_server("busy", "192.0.2.15", 22, "monitor")
    db.save_snapshot(
        server_id,
        cpu_percent=90,
        mem_used_bytes=GB,
        mem_total_bytes=2 * GB,
        network_json="[]",
        ports_json="[]",
        error=None,
    )
    body = logged_in.get("/").get_data(as_text=True)
    assert "status-warn" in body
    assert "High CPU" in body


def test_api_and_write_methods(logged_in):
    anonymous = logged_in.application.test_client()
    server_id = db.add_server("edge", "192.0.2.10", 22, "monitor")
    db.save_snapshot(
        server_id,
        cpu_percent=10,
        mem_used_bytes=GB,
        mem_total_bytes=2 * GB,
        network_json="[]",
        ports_json="[]",
        error=None,
    )
    anonymous_response = anonymous.get("/api/servers")
    assert anonymous_response.status_code == 302
    assert anonymous_response.headers["Location"].endswith("/login")
    anonymous_detail = anonymous.get(f"/api/servers/{server_id}/metrics")
    assert anonymous_detail.status_code == 302

    fleet = logged_in.get("/api/servers")
    assert fleet.status_code == 200
    assert fleet.json["servers"][0]["cpu"] == "10.0%"
    detail = logged_in.get(f"/api/servers/{server_id}/metrics")
    assert detail.status_code == 200
    assert detail.json["memory"] == "50% · 1.0 GB / 2.0 GB"
    missing = logged_in.get("/api/servers/999/metrics")
    assert missing.status_code == 404
    assert missing.json == {"error": "Not found"}
    assert "999" not in missing.get_data(as_text=True)

    for path in ("/api/servers", f"/api/servers/{server_id}/metrics"):
        for method in ("post", "put", "patch", "delete"):
            response = getattr(logged_in, method)(path)
            assert response.status_code in {405, 404}


def test_refresh_script_does_not_use_inner_html():
    text = Path("static/refresh.js").read_text(encoding="utf-8")
    assert "innerHTML" not in text
    assert "textContent" in text
    assert "same-origin" in text


def test_ci_workflow_runs_pytest_without_ssh_or_secrets():
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pytest" in text
    assert "pull_request_target" not in text
    assert "secrets." not in text
    lowered = text.lower()
    assert "ssh" not in lowered
    assert "contents: read" in text


def test_unreachable_error_string_is_generic():
    assert present.safe_error({"error": sshutil.SSH_FAILED}) == "Could not connect."
    assert present.safe_error({"error": "OpenSSH banner"}) == "Could not connect."
