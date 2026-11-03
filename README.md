# Server Monitor

Local demo for Linux server monitoring. Sign in, register hosts, and read CPU, memory, network, and listening ports collected over SSH. The fleet and detail pages are read-only. The app binds to `127.0.0.1` by default. Do not expose this app to the internet.

## Requirements

Python 3.10 or newer.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

The demo username is `admin`. Set your own hash. The app reads `SECRET_KEY` and `ADMIN_PASSWORD_HASH` from the environment and refuses to start if `SECRET_KEY` is missing.

Create a hash with Werkzeug, then export both variables:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"
export SECRET_KEY="paste-a-long-random-string"
export ADMIN_PASSWORD_HASH="paste-the-hash"
```

`.env.example` lists the variable names with placeholders only. Do not commit a real secret or password hash.

Point `SSH_KEY_PATH` at the private key used for every demo host, and authorize the matching public key on the target. The key file should be mode `0600`:

```bash
chmod 0600 /path/to/private-key
export SSH_KEY_PATH="/path/to/private-key"
```

If `SSH_KEY_PATH` is missing or not a file, collection is skipped and the UI shows an error. The key is not stored in SQLite or written to the log.

Targets must already be in `known_hosts`. The app rejects unknown host keys. Add one with:

```bash
ssh-keyscan -H -p 22 your.host >> ~/.ssh/known_hosts
```

## Run

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

The process listens on `127.0.0.1` port `5000`. Set `HOST` and `PORT` to override that address. Debug mode stays off unless `FLASK_DEBUG=1`.

The first run creates `monitor.db` in the project directory (or `DATABASE_PATH`). That file is gitignored and is not committed. It holds the server list and the latest sample for each host. SSH passwords are not stored.

All monitoring pages require sign-in. Use the Logout control in the top bar to end the session.

The session cookie is HttpOnly and SameSite=Lax, Secure only when the request is not plain local HTTP, and it expires after 8 hours idle (`SESSION_IDLE_HOURS`).

## Routes

| Method | Path | Page |
|--------|------|------|
| GET, POST | `/login` | Sign in as `admin`. |
| POST | `/logout` | Clear the session and return to sign-in. |
| GET | `/` | Fleet: name, host, status, CPU %, memory %, last check. |
| GET | `/servers/<id>` | Detail for one host. Unknown ids return a generic 404. |
| GET | `/admin/servers` | Inventory. Add and remove hosts here. |
| POST | `/admin/servers` | Add a host. |
| POST | `/admin/servers/test` | Try SSH without saving the host. |
| POST | `/admin/servers/<id>/delete` | Remove a host and stop collection for it. |
| GET | `/api/servers` | JSON for the fleet refresh. |
| GET | `/api/servers/<id>/metrics` | JSON for the detail refresh. |

The JSON routes exist so the pages can refresh. They are GET only.

## Inventory

Adding a Linux host needs a display name, host (IP or DNS), SSH port (default 22), and SSH user. Use Test connection before relying on a host. A failed test does not save the row. Removing a server stops future collection for that host.

## Metrics

The UI reads the cached snapshot, not a live SSH session. The poller runs every 15 seconds (`POLL_INTERVAL_SECONDS` overrides that default) and keeps only the latest sample per host. Pages refresh every 15 seconds.

CPU is a single percent computed from two `/proc/stat` samples. Memory is shown as a percent and as MB/GB. Network shows RX/TX bytes per interface, and a simple rate once two samples exist. The loopback interface is hidden. Listening ports come from Ubuntu-like `ss` output (protocol, address, port, and a process name only when `ss -tulnp` works without sudo). A missing metric shows “metric unavailable”. An unreachable host stays on the fleet list with a short error.

Green means the last poll succeeded, amber means CPU is at least 90%, and red means the last poll recorded an error.

Open a fleet row to see that host’s CPU, memory, network, and ports.

## Logs

Poll start, duration, and SSH failures are written to stdout. Logs do not include passwords, key contents, or command output. When a host stays red, read that stdout for the `ssh failure` line.

## Demo script

Do not expose this app to the internet. It binds to `127.0.0.1` unless you set `HOST`. Keep the private key mode `0600`.

1. Export `SECRET_KEY`, `ADMIN_PASSWORD_HASH`, and `SSH_KEY_PATH`.
2. Run `python app.py` and open `http://127.0.0.1:5000`.
3. Sign in as `admin`.
4. Open Servers, enter the host, and press Test connection.
5. Press Add server and wait 15 seconds.
6. Open the fleet row to see the detail page.
7. Remove the host. Collection for that host stops.

## Tests

```bash
pytest
```

Tests do not need SSH and do not need a browser. Inventory tests use a temporary database. Collector tests are mocked. The poller test uses the same stub. Parser fixtures live under `tests/fixtures/`.

## CI

CI runs pytest on GitHub. The workflow does not deploy, print secrets, or SSH to hosts. Deploy stays `python app.py` on the machine running the app.
