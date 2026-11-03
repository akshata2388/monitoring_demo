# Implementation TODO

Local demo only. Work **one checkbox at a time**. Do not skip the security or docs line under a step.

Source: [requirements.md](requirements.md). Stack: Python, Flask, SQLite, SSH pull. Bind `127.0.0.1:5000`.

---

## 1. Project initialization and basic UI

- [x] **1.1 Scaffold the repo**
  - Add `app.py` (or `app/` package), `requirements.txt` with pinned Flask, `tests/`, and `.gitignore`.
  - **Security:** Ignore `.env`, `*.db`, `*.pem`, and `__pycache__`. Do not commit secrets or SSH keys.
  - **Docs:** `README.md` with Python 3.10+, venv, `pip install -r requirements.txt`.

- [x] **1.2 Run a blank Flask app locally**
  - Start with one command (`python app.py`). Listen on `127.0.0.1`, port `5000` (override with `HOST` / `PORT`).
  - **Security:** Debug mode off unless `FLASK_DEBUG=1`. Do not bind `0.0.0.0` by default.
  - **Docs:** README “Run” section: URL `http://127.0.0.1:5000`.

- [x] **1.3 Base layout**
  - Shared template: top bar (product name), simple responsive CSS, readable type.
  - **Security:** No third-party scripts. Escape all template output (Jinja default).
  - **Docs:** Note in README that the UI is a local read-only demo shell.

- [x] **1.4 Fleet placeholder (read-only)**
  - `GET /` shows an empty server table: name, host, status, CPU, memory. No action buttons.
  - **Security:** No forms and no write endpoints on this page.
  - **Docs:** List the route in README.

- [x] **1.5 Server detail placeholder (read-only)**
  - `GET /servers/<id>` shows empty CPU, Memory, Network, and Ports sections (sample id is fine).
  - **Security:** Treat `id` as display-only. No shell or database calls yet.
  - **Docs:** Mention the detail route in README.

---

## 2. Sign-in and unit tests

- [x] **2.1 Config for secrets**
  - Read `SECRET_KEY` and `ADMIN_PASSWORD_HASH` from the environment. Add `.env.example` with placeholders only.
  - **Security:** Refuse to start if `SECRET_KEY` is missing. Never store or log the plaintext password. Username is `admin` only.
  - **Docs:** README: how to create a hash (one Werkzeug or bcrypt command) and export the two variables.

- [x] **2.2 Login page**
  - `GET/POST /login`. Check the password against the hash. On success, set a session and redirect to `/`.
  - **Security:** Same error text for bad username or password. Do not log the password. Add a CSRF token on the form.
  - **Docs:** README: demo username `admin` and “set your own hash”.

- [x] **2.3 Session cookie**
  - Cookie flags: `HttpOnly`, `SameSite=Lax`. `Secure` only when not on plain local HTTP.
  - **Security:** Idle lifetime 8 hours (configurable). Session holds only “logged in”, not the password.
  - **Docs:** One line in README on cookie flags and timeout.

- [x] **2.4 Logout**
  - `POST /logout` clears the session and returns to `/login`.
  - **Security:** POST only, with CSRF. No logout via GET.
  - **Docs:** README: use the Logout control.

- [x] **2.5 Protect pages**
  - Require a session for `/`, `/servers/<id>`, and later `/admin/*` and `/api/*`. Allow `/login` and static files only.
  - **Security:** Redirect anonymous users to `/login`. Do not leak metrics in the redirect response.
  - **Docs:** README: all monitoring pages require sign-in.

- [x] **2.6 Unit tests for auth**
  - Pytest: wrong password rejected, correct password sets session, anonymous `/` redirects, logout clears session.
  - **Security:** Tests use a fake hash and secret. No real credentials in the repo.
  - **Docs:** README: `pytest` command and that tests do not need SSH.

---

## 3. CI (GitHub Actions)

- [x] **3.1 Workflow file**
  - `.github/workflows/ci.yml` on push and pull request: checkout, Python 3.10+, install `requirements.txt`, run `pytest`.
  - **Security:** Pin action versions by SHA or tag. No secrets in the workflow. Do not print env. CI must not SSH to real hosts.
  - **Docs:** README: “CI runs pytest on GitHub”.

- [x] **3.2 Keep CI local-demo sized**
  - Single job. Fail the job if tests fail. No deploy step.
  - **Security:** Workflow has no `pull_request_target` and no write permissions beyond default read.
  - **Docs:** Note in README that deploy stays `python app.py` on the machine running Cursor.

---

## 4. Server inventory (SQLite)

- [x] **4.1 Database file and schema**
  - Create `servers` on startup (`id`, `name`, `host`, `ssh_port`, `ssh_user`, `enabled`, `created_at`). SQLite file under the project, gitignored.
  - **Security:** DB is local only. No SSH passwords in the table (key path comes from env later).
  - **Docs:** README: DB file is created on first run and is not committed.

- [x] **4.2 List servers (admin page, still empty of metrics)**
  - `GET /admin/servers` shows rows from SQLite. Link from the top bar.
  - **Security:** Login required. Render text with auto-escape.
  - **Docs:** README: admin page path.

- [x] **4.3 Add a server**
  - `POST /admin/servers` with name, host, SSH port (default 22), SSH user. Validate non-empty name/host, port 1–65535, user charset.
  - **Security:** CSRF. Reject unexpected fields. Do not pass host or user into a shell on the app machine.
  - **Docs:** README: fields required to add a Linux host.

- [x] **4.4 Remove a server**
  - `POST /admin/servers/<id>/delete` removes the row.
  - **Security:** POST + CSRF. Login required. Confirm id exists before delete.
  - **Docs:** README: remove stops future collection for that host.

- [x] **4.5 Tests for inventory**
  - Pytest with a temp SQLite file: add, list, invalid port rejected, delete.
  - **Security:** Tests must not open network sockets.
  - **Docs:** README: inventory tests use a temp database.

---

## 5. SSH collector (read-only)

- [x] **5.1 Config for the key**
  - `SSH_KEY_PATH` from the environment. One key for all demo hosts.
  - **Security:** If the path is missing or not a file, skip SSH and show an error. Do not store key material in SQLite or logs. Recommend mode `0600` in the docs.
  - **Docs:** README: point `SSH_KEY_PATH` at a private key; authorize it on the target.

- [x] **5.2 SSH connect helper**
  - Connect with a short timeout (for example 5s). Close the client in a `finally` block.
  - **Security:** No `AutoAddPolicy` without a written demo note. Prefer the system `known_hosts`. No remote shell built from string concatenation of user input.
  - **Docs:** README: targets must already be in `known_hosts` (one `ssh-keyscan` example).

- [x] **5.3 Test connection**
  - `POST /admin/servers/test` attempts SSH and returns success or a short error. Do not save on failure unless the user submits Add separately.
  - **Security:** Login + CSRF. Generic error to the UI; detailed reason only in server logs. No command execution beyond a no-op connect or `true`.
  - **Docs:** README: use Test before relying on a host.

- [x] **5.4 Tests with a fake SSH client**
  - Unit-test success, timeout, and auth failure using a stub. No real SSH in CI.
  - **Security:** CI has no network to production hosts.
  - **Docs:** README: collector tests are mocked.

---

## 6. Metric parsers (one at a time)

Remote commands stay a fixed allow-list. Parse failures become “metric unavailable”, not an app crash.

- [x] **6.1 CPU**
  - Read `/proc/stat`, compute overall CPU %. Store on the snapshot model (column or JSON).
  - **Security:** Command string is a constant. Timeout the exec. Do not log full remote output.
  - **Docs:** README: CPU is a single percent from `/proc/stat`.

- [x] **6.2 Memory**
  - Parse `/proc/meminfo` into used and total bytes.
  - **Security:** Same allow-list and timeout rules as CPU.
  - **Docs:** README: memory shown as percent and MB/GB.

- [x] **6.3 Network**
  - Parse `/proc/net/dev` per interface (skip `lo` in the UI). Keep the previous counters in memory so the UI can show a rate.
  - **Security:** Read-only file read only. Cap the number of interfaces stored.
  - **Docs:** README: RX/TX bytes and a simple rate when two samples exist.

- [x] **6.4 Listening ports**
  - Parse `ss -tuln` (process name only if `ss -tulnp` works without sudo). Show protocol, address, port.
  - **Security:** Do not require sudo. Drop process names if the command fails and still show ports.
  - **Docs:** README: listening ports only; tested on Ubuntu-like `ss`.

- [x] **6.5 Parser unit tests**
  - Feed fixture text files for each parser, including one bad sample per metric.
  - **Security:** Fixtures contain no real hostnames, keys, or customer data.
  - **Docs:** README: fixtures live under `tests/fixtures/`.

---

## 7. Poller and snapshots

- [x] **7.1 `metric_snapshots` table**
  - Columns from the PRD: `server_id`, `collected_at`, CPU, memory, `network_json`, `ports_json`, `error`. Keep the latest row per server for the demo.
  - **Security:** JSON is data, not code. Do not `eval` it.
  - **Docs:** README: only the latest sample is kept.

- [x] **7.2 Background poll loop**
  - Every 15 seconds, poll enabled servers one at a time. Write the snapshot. Record duration and SSH errors in logs.
  - **Security:** Fixed command list. Per-host timeout. A failure on one host must not stop the loop.
  - **Docs:** README: default interval 15s and that the UI reads the cache, not live SSH.

- [x] **7.3 Tests for the poller**
  - Fake SSH returns fixture output. Assert a snapshot row and an error row when the stub raises.
  - **Security:** No real network.
  - **Docs:** README: poller test uses the stub.

---

## 8. Wire the read-only UI to data

- [x] **8.1 Fleet from the database**
  - `GET /` lists servers plus last CPU %, memory %, status, and last check time.
  - **Security:** Still no write controls. Login required. Escape names and hosts.
  - **Docs:** README: fleet columns.

- [x] **8.2 Status colors**
  - Green when the last poll succeeded, red when `error` is set, amber when CPU ≥ 90% (constant in code).
  - **Security:** Threshold is not user input.
  - **Docs:** README: color meanings in one sentence.

- [x] **8.3 Detail page**
  - `GET /servers/<id>` shows CPU, memory, network table, and ports from the latest snapshot. Unknown id returns 404.
  - **Security:** Login required. 404 body stays generic.
  - **Docs:** README: open a row to see detail.

- [x] **8.4 Read-only JSON for refresh**
  - `GET /api/servers` and `GET /api/servers/<id>/metrics` return the same cached data.
  - **Security:** Session required. GET only. No methods that insert, update, or delete.
  - **Docs:** README: JSON routes exist for the UI refresh only.

- [x] **8.5 Auto-refresh**
  - Fleet and detail fetch JSON every 15s and update the page without a full reload. Manual refresh button is optional and still GET.
  - **Security:** Same-origin fetch only. No `innerHTML` with unescaped server strings (use `textContent` or a template that escapes).
  - **Docs:** README: pages refresh every 15s.

- [x] **8.6 Partial failure**
  - If one metric is missing, show “metric unavailable” in that section. Other servers and sections still render.
  - **Security:** Show a short error string, not stack traces or SSH banners.
  - **Docs:** README: unreachable hosts stay on the fleet list with an error.

- [x] **8.7 UI tests**
  - Flask test client: fleet and detail render fixture snapshots; API returns 302 or 401 when logged out and 200 when logged in.
  - **Security:** Assert write methods on `/api/*` are not implemented (405 or 404).
  - **Docs:** README: UI tests do not need a browser.

---

## 9. Finish the local demo

- [x] **9.1 Logging**
  - Log poll start, duration, and SSH failure at INFO/WARNING. Do not log passwords, key contents, or full command output.
  - **Security:** Logs go to stdout only for the demo.
  - **Docs:** README: where to look when a host stays red.

- [x] **9.2 Demo walkthrough**
  - Add a short “Demo script” to the README: login, add host, test SSH, wait 15s, open detail, remove host.
  - **Security:** Repeat localhost bind, key permissions, and “do not expose this app to the internet”.
  - **Docs:** This step is the demo script. Keep it under one screen.

- [x] **9.3 CI still green**
  - Push the workflow path only. Confirm GitHub Actions runs pytest with no SSH and no secrets.
  - **Security:** If a test tries to open port 22, delete that test.
  - **Docs:** README stays the only setup guide.

---

## Out of scope for this list

Disk, load, uptime, top processes, alerting, extra user accounts, RBAC, Windows, Kubernetes, agents, and any deploy beyond `python app.py` on the local machine.
