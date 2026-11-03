# Server Monitor

Local read-only demo shell for Linux server monitoring. The pages show an empty fleet and an empty server detail view. They do not collect metrics or change anything on a host.

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

## Run

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

The process listens on `127.0.0.1` port `5000`. Set `HOST` and `PORT` to override that address. Debug mode stays off unless `FLASK_DEBUG=1`.

The UI is a local read-only demo shell. All monitoring pages require sign-in. Use the Logout control in the top bar to end the session.

The session cookie is HttpOnly and SameSite=Lax, Secure only when the request is not plain local HTTP, and it expires after 8 hours idle (`SESSION_IDLE_HOURS`).

## Routes

| Method | Path | Page |
|--------|------|------|
| GET, POST | `/login` | Sign in as `admin`. |
| POST | `/logout` | Clear the session and return to sign-in. |
| GET | `/` | Fleet table: name, host, status, CPU, memory. Empty until servers exist. |
| GET | `/servers/<id>` | Server detail placeholder. Sections: CPU, Memory, Network, and Ports. The id is display-only. |

Example: [http://127.0.0.1:5000/servers/1](http://127.0.0.1:5000/servers/1).

## Tests

```bash
pytest
```

Tests do not need SSH. They use a fake secret and password hash.
