# Product Requirements Document (PRD)

## Demo Monitoring Infrastructure — Linux Servers

| Field | Value |
|--------|--------|
| **Document** | Software specification (PRD) |
| **Product** | Local demo: Linux server monitoring UI |
| **Version** | 1.0 (demo) |
| **Status** | Draft |
| **Tech stack** | Python, Flask, attractive read-only UI |

---

## 1. Summary

### 1.1 Problem

Operations and development teams must **SSH into each Linux server** to inspect real-time **CPU, memory, network, and port** usage. That is slow, does not scale for quick checks, and duplicates effort across L1, L2, and L3.

### 1.2 Solution (demo)

A **locally hosted** web application that:

- Collects metrics from registered Linux hosts **over SSH** (no per-server agent for v1).
- Presents a **friendly, read-only** dashboard for viewing health and usage.
- Allows a single **admin** user to **sign in** and **manage the server list** (add/remove).

This is a **demonstration** system, not production monitoring. Scope, security, and operations are intentionally minimal so it can run on the same machine as the development environment (e.g. Cursor workspace host).

### 1.3 Users

| Persona | Need |
|---------|------|
| **L1** | Quick glance: is the box up, CPU/RAM high, ports listening? |
| **L2** | Same views with enough detail to triage before SSH |
| **L3 / app dev** | Fleet list + per-host detail without logging in to every host |
| **Admin (demo)** | Register/unregister hosts to monitor |

All personas use the **same read-only views** after sign-in. There is **no role-based access** in v1.

---

## 2. Goals and non-goals

### 2.1 Goals

- Replace routine “log in just to look” checks for **CPU, memory, network, and ports** on **Linux** servers.
- **Minimal local setup**: install dependencies, configure admin password, run one process, open browser.
- **Clear separation**: metrics and dashboards are **read-only**; only **server inventory** changes require admin actions.

### 2.2 Non-goals (v1)

- Alerting (email, Slack, PagerDuty).
- Multi-user accounts, RBAC, or audit trails beyond basic session.
- Windows, macOS agents, Kubernetes, or cloud-native discovery.
- High availability, horizontal scaling, or long-term metrics retention at production scale.
- Installing a persistent agent on target servers (SSH-only collection).
- Writable “control plane” (no restart services, kill processes, or change config from UI).

---

## 3. Decisions (from stakeholder input)

The following items were explicitly confirmed; other details in this document use **demo defaults** (see §3.2).

| # | Topic | Decision |
|---|--------|----------|
| **1** | **Metrics scope** | **In scope:** CPU, memory, network utilization, and **port usage** (listening services). **Out of scope for v1:** disk, load average, uptime widgets, top-N processes (may be added later without changing architecture). |
| **5** | **Collection model** | **Pull via SSH** from the Flask application host. Commands/read `/proc`, `ss`/`netstat`, and standard CLI tools on targets. |
| **11** | **Authentication** | **Single shared user:** default username `admin`. Password stored as a **hash** (not plaintext). |
| **15** | **Read-only vs writes** | **Read-only UI** for all monitoring data. **Write operations** limited to: sign-in/sign-out and **admin server list** (add/remove servers). No API to mutate metrics or remote server state. |
| **18** | **Run model** | **Single process**, local deployment, started with **one command** (e.g. `python app.py` or `flask run`), default HTTP port **5000** (overridable via env). |

### 3.2 Demo defaults (assumed where not specified)

| Area | Default |
|------|---------|
| **History** | Live / near-live only; no long-term chart database required for demo. |
| **Ports** | **Listening ports** (address, port, process name where available). |
| **Refresh** | Auto-refresh dashboards every **15 seconds**; manual refresh optional. |
| **SSH** | Per-server: display name, host/IP, SSH port (default 22), SSH username. Auth via **SSH private key path** (app config) or password field stored encrypted in local DB—demo may use key-based auth only to reduce scope. |
| **Reachability** | Target hosts must be reachable from the **machine running the app** (same laptop/VM as Cursor). |
| **Server lifecycle** | Add, remove, optional **Test connection** on add; edit host optional for v1. |
| **Scale** | Design for **≤ 20** hosts in demo. |
| **Password config** | Admin password hash via **environment variable** or local config file; default password documented for first login in README only. |
| **Session** | Cookie-based session; **Logout** button; idle timeout **8 hours** (configurable). |
| **UI structure** | **Fleet table** (all servers, summary columns) → **Server detail** (CPU, memory, network, ports). |
| **Persistence** | **SQLite**: server inventory, optional last-known snapshot per poll. |
| **Dependencies** | OpenSSH client on app host; on targets: typical userland (`bash`, `ss` or `netstat`, `/proc`). |

---

## 4. Functional requirements

### 4.1 Feature 1 — User-friendly read-only monitoring UI

| ID | Requirement | Priority |
|----|-------------|----------|
| F1.1 | After sign-in, user sees a **fleet dashboard**: server name, host, reachability status, last check time, summary CPU % and memory % (last sample). | Must |
| F1.2 | User can open a **server detail** page with sections: **CPU**, **Memory**, **Network**, **Ports**. | Must |
| F1.3 | All monitoring views are **read-only** (no buttons that change server state). | Must |
| F1.4 | UI is **responsive** and visually polished (modern layout, clear typography, status colors for up/down/warn). | Must |
| F1.5 | Data updates via **auto-refresh** (default 15s) without full page reload where practical (AJAX/fetch or HTMX acceptable). | Should |
| F1.6 | Unreachable hosts show **clear error** (SSH failure, timeout) without breaking the whole page. | Must |

**Acceptance (F1):** With three registered hosts, a signed-in user can compare fleet status and drill into one host’s CPU/memory/network/ports without using SSH directly.

---

### 4.2 Feature 2 — Sign-in (admin, hashed password)

| ID | Requirement | Priority |
|----|-------------|----------|
| F2.1 | **Login page** with username and password. Default username **`admin`**. | Must |
| F2.2 | Password verification uses a **secure hash** (e.g. bcrypt, argon2, or Werkzeug hash); never store or log plaintext passwords. | Must |
| F2.3 | Successful login creates a **server-side session**; unauthenticated users cannot view dashboards or server APIs. | Must |
| F2.4 | **Logout** clears session and returns to login. | Must |
| F2.5 | Initial admin password hash supplied via **env/config** for demo; optional README note for default demo password. | Must |

**Acceptance (F2):** Wrong password rejected; correct password grants access; session required for all monitoring routes.

---

### 4.3 Feature 3 — Register Linux servers for monitoring

| ID | Requirement | Priority |
|----|-------------|----------|
| F3.1 | **Admin-only** screen (same `admin` user) to **add** a Linux server: display name, hostname/IP, SSH port, SSH username. | Must |
| F3.2 | **Remove** server from inventory (stops polling; removes from UI). | Must |
| F3.3 | Optional **Test connection** on add: SSH handshake success/failure before save. | Should |
| F3.4 | Background **poller** connects periodically (aligned with refresh interval) and stores **latest snapshot** for UI. | Must |
| F3.5 | Only **Linux** targets are supported; UI labels OS type as Linux. | Must |

**Acceptance (F3):** Admin adds a valid Linux host; within one poll cycle, fleet and detail pages show metrics or a defined error state.

---

## 5. Metrics specification (collection via SSH)

Collection runs on the app host; each poll opens an SSH session (or reuses a pool for demo simplicity), runs read-only commands, parses output.

| Metric | Source (illustrative) | Display |
|--------|------------------------|---------|
| **CPU** | `/proc/stat` or `top`/`mpstat` one-shot | Overall usage % (user + system; idle derived) |
| **Memory** | `/proc/meminfo` | Used / total % and absolute (MB/GB) |
| **Network** | `/proc/net/dev` or `ip -s link` | RX/TX bytes per interface; rates if two samples kept |
| **Ports** | `ss -tulnp` or `netstat -tulnp` | Protocol, local address:port, process name (if permitted) |

**Constraints:**

- Commands must be **read-only**; no `sudo` requirement unless documented for demo hosts.
- Parse failures surface as **“metric unavailable”** for that section, not a 500 for the entire app.

---

## 6. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NF1 | **Local-only demo**: bind to `127.0.0.1` by default; document how to bind `0.0.0.0` if needed on LAN. |
| NF2 | **Performance**: fleet page loads in &lt; 3s with up to 20 hosts using cached last poll. |
| NF3 | **Security (demo level)**: hashed admin password, session secret from env, SSH keys file permissions documented; not hardened for internet exposure. |
| NF4 | **Operability**: structured logging for SSH errors and poll duration (stdout or simple file). |
| NF5 | **Maintainability**: Python 3.10+; dependencies pinned in `requirements.txt`. |

---

## 7. Architecture (high level)

```text
┌─────────────────────────────────────────────────────────┐
│  Browser (read-only dashboards + admin server CRUD)      │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP (session cookie)
┌───────────────────────────▼─────────────────────────────┐
│  Flask app (single process)                              │
│  • Auth (admin / hashed password)                        │
│  • REST or server-rendered routes + JSON for refresh     │
│  • Poller thread/job: SSH → parse → SQLite snapshot      │
└───────────────────────────┬─────────────────────────────┘
                            │ SSH (22/tcp)
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   Linux host A        Linux host B        Linux host C
```

**Components (minimal):**

- **Web layer**: Flask routes, Jinja2 templates (or lightweight SPA-style templates with fetch).
- **Auth module**: login, session, `@login_required` on all routes except login/static.
- **Inventory**: SQLite table `servers`.
- **Collector**: SSH client (e.g. Paramiko), metric parsers, `metrics_latest` table or in-memory cache with DB backup.
- **Scheduler**: simple loop or APScheduler interval job (15s per server staggered if needed).

---

## 8. Data model (SQLite)

### 8.1 `servers`

| Column | Type | Notes |
|--------|------|--------|
| id | INTEGER PK | |
| name | TEXT | Display name |
| host | TEXT | IP or DNS |
| ssh_port | INTEGER | Default 22 |
| ssh_user | TEXT | |
| enabled | BOOLEAN | Default true |
| created_at | TIMESTAMP | |

### 8.2 `metric_snapshots` (optional but recommended for demo)

| Column | Type | Notes |
|--------|------|--------|
| id | INTEGER PK | |
| server_id | FK | |
| collected_at | TIMESTAMP | |
| cpu_percent | REAL | |
| mem_used_bytes | INTEGER | |
| mem_total_bytes | INTEGER | |
| network_json | TEXT | Per-interface counters |
| ports_json | TEXT | Listening ports list |
| error | TEXT | Null if OK |

---

## 9. API / routes (conceptual)

All routes except `/login` require authentication.

| Method | Path | Purpose | Writes? |
|--------|------|---------|--------|
| GET/POST | `/login` | Sign in | Session only |
| POST | `/logout` | Sign out | Session only |
| GET | `/` | Fleet dashboard | No |
| GET | `/servers/<id>` | Server detail | No |
| GET | `/api/servers` | JSON fleet + latest metrics | No |
| GET | `/api/servers/<id>/metrics` | JSON detail metrics | No |
| GET/POST | `/admin/servers` | List / add server | Yes (inventory) |
| POST | `/admin/servers/<id>/delete` | Remove server | Yes (inventory) |
| POST | `/admin/servers/test` | Test SSH | No remote mutation |

---

## 10. UI guidelines

- **Theme**: Clean dashboard (cards, tables, subtle charts for CPU/memory if desired).
- **Status**: Green / amber / red for reachability and threshold hints (e.g. CPU &gt; 90% amber/red)—thresholds configurable constants, not user-editable in v1.
- **Navigation**: Top bar with product name, fleet link, admin servers link, logout.
- **Copy**: Plain language for L1 (“Last updated”, “Unable to connect via SSH”).

---

## 11. Local deployment (minimal steps)

Intended for the machine where Cursor runs the project.

1. **Prerequisites**: Python 3.10+, `pip`, OpenSSH client, network/SSH access to demo Linux hosts.
2. **Clone/open** project directory.
3. **Create venv** (recommended): `python -m venv .venv && source .venv/bin/activate`
4. **Install**: `pip install -r requirements.txt`
5. **Configure** (env or `.env` example):
   - `SECRET_KEY` — Flask session secret
   - `ADMIN_PASSWORD_HASH` — hash of demo password, or script to generate hash once
   - `SSH_KEY_PATH` — optional default private key for all servers
   - `HOST=127.0.0.1`, `PORT=5000`
6. **Initialize DB**: first run creates SQLite file (or `flask init-db` if implemented).
7. **Run**: `python app.py` (or `flask run --port 5000`).
8. **Use**: Open `http://127.0.0.1:5000`, login as `admin`, add servers under admin, view dashboards.

**Demo SSH tip:** Pre-authorize key on target `~/.ssh/authorized_keys` to avoid storing passwords.

---

## 12. Testing and demo script

| Step | Action | Expected |
|------|--------|----------|
| 1 | Start app locally | Login page on port 5000 |
| 2 | Login as admin | Fleet page (empty or seeded) |
| 3 | Add localhost or VM IP | Test connection succeeds |
| 4 | Wait one poll interval | CPU/memory/network/ports populated or partial |
| 5 | Stop SSH on target or wrong IP | Fleet shows error; other hosts still work |
| 6 | Remove server | Disappears from fleet; polling stops |

---

## 13. Risks and mitigations (demo)

| Risk | Mitigation |
|------|------------|
| SSH rate / serial polls slow with many hosts | Stagger polls; show last cached snapshot with timestamp |
| Parsing differs across distros | Document tested distros (e.g. Ubuntu 22.04); defensive parsers |
| Storing SSH secrets | Prefer key auth; encrypt at rest if passwords stored |
| Users expose app to internet | Document localhost-only default; not production-ready |

---

## 14. Future enhancements (post-demo)

- Disk, load, uptime, top processes (extends Q1 scope).
- Per-team tags and filters; read-only “viewer” vs “admin” roles.
- Short history charts (24h) with roll-up tables.
- Lightweight read-only agent if SSH is undesirable.

---

## 15. Glossary

| Term | Definition |
|------|------------|
| **Fleet** | All registered servers shown in one table |
| **Poll** | One SSH-based metrics collection cycle for one server |
| **Snapshot** | Latest parsed metrics stored for UI display |

---

## 16. Document history

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-11-03 | — | Initial PRD from stakeholder features and decisions on metrics scope, SSH collection, single admin, read-only UI with admin inventory, local port 5000 |
