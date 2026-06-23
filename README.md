# CampusFix

CampusFix is a small Flask-based marketplace for university students to post problems/tasks and get help from other students. The app is a single-file Flask application (app.py) that uses PostgreSQL for persistence and server-rendered Jinja2 templates in templates/ with static assets in static/.

> Important: This repository does not include a README until now. I created this README to document running, deploying, and maintaining the app.

## Stack
- Language: Python 3
- Framework: Flask (server-rendered Jinja2 templates)
- Notable libraries: Flask, psycopg (psycopg[binary]), Werkzeug

## What's included (top-level)
```
app.py               # Main Flask application and DB init
requirements.txt     # Python dependencies
templates/           # Jinja2 templates (HTML views)
static/              # Static assets (css, uploads folder created at runtime)
.gitignore
```

## How it works (runtime shape)
- app.py is a single Flask app that connects to a PostgreSQL database via psycopg. On startup (when run directly) it calls `init_db()` which will create required tables if they don't exist.
- The web UI is rendered from templates/ and uses Bootstrap 5 from CDN.
- User session data are stored using Flask sessions; a secret key is currently hard-coded in app.py (you should change that for production).

## Quickstart — run locally (recommended for development)
Prerequisites:
- Python 3.10+ installed
- PostgreSQL server running and accessible

Steps:

1. Clone the repo

```bash
git clone https://github.com/kingsdisease19/campusfix.git
cd campusfix
```

2. Create a Python virtual environment and install deps

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

3. Create the Postgres database

By default app.py uses the following DB constants near the top of the file:

- DB_HOST = "localhost"
- DB_NAME = "campusfix"
- DB_USER = "postgres"

If your Postgres user has a password or you use a different host/name/user, either edit those constants in app.py or set environment variables and modify the file (see Security notes).

Create the database and (optionally) a user:

```bash
# as a postgres superuser
psql -U postgres -c "CREATE DATABASE campusfix;"
# (optional) create a dedicated user:
# psql -U postgres
# CREATE USER campus_user WITH PASSWORD 'strongpassword';
# CREATE DATABASE campusfix OWNER campus_user;
```

4. Run the app

```bash
python app.py
```

When started as `__main__` the app calls init_db() which creates the tables automatically.

Open http://127.0.0.1:5000 in your browser.

## Environment & secrets (important)
- The app currently contains a hard-coded `app.secret_key` in app.py. For production you must replace this with a secret from an environment variable.
- Also avoid hard-coding DB credentials. I recommend changing app.py to read DB config and secret key from environment variables (example snippet below).

Example minimal environment-driven config (replace the top of app.py):

```python
import os

app.secret_key = os.getenv('CAMPUSFIX_SECRET') or 'dev-secret'
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'campusfix')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD')  # optional

# Then pass DB_PASSWORD to psycopg.connect when present
```

## Deploy to production — basic options
Pick one of these depending on comfort and budget. The app is a WSGI Flask app and can be served with Gunicorn (recommended) behind a reverse proxy.

Option A — Gunicorn + systemd (Linux VM)
1. Install Python, create a virtualenv, install requirements (same as Quickstart).
2. Create a systemd service (example below) and start it behind nginx as a reverse proxy.

Example Gunicorn systemd service (/etc/systemd/system/campusfix.service):

```
[Unit]
Description=CampusFix Flask app
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/campusfix
Environment=CAMPUSFIX_SECRET=replace_with_strong_secret
Environment=DB_HOST=localhost
Environment=DB_NAME=campusfix
Environment=DB_USER=campus_user
Environment=DB_PASSWORD=supersecret
ExecStart=/path/to/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:app

[Install]
WantedBy=multi-user.target
```

Then use nginx to proxy from port 80 to 127.0.0.1:8000 and enable HTTPS with Certbot.

Option B — Docker
Create a Dockerfile and run with a Postgres database container or managed Postgres. Example Dockerfile (simple):

```
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --upgrade pip && pip install -r requirements.txt
ENV FLASK_ENV=production
ENV CAMPUSFIX_SECRET="replace-me"
EXPOSE 5000
CMD ["gunicorn","-w","4","-b","0.0.0.0:5000","app:app"]
```

Option C — Platform-as-a-Service (Render, Railway, Fly, Heroku)
- Create a service, connect your GitHub repo, set required environment variables (CAMPUSFIX_SECRET, DB_HOST, DB_NAME, DB_USER, DB_PASSWORD), and set the start command to `gunicorn -w 4 -b 0.0.0.0:5000 app:app`.
- For Heroku-like platforms you may need to add a `Procfile` with: `web: gunicorn app:app` and ensure requirements.txt is present (it is).

## Database migrations
- There is no migration framework (Alembic/Flask-Migrate) in this repo. app.py's `init_db()` will create missing tables/columns on startup, which is convenient but not robust for production schema changes. For production consider adding Alembic and migration scripts.

## Security & hardening checklist
- Remove or rotate the hard-coded secret (app.secret_key) and DB credentials. Use environment variables or secrets management.
- Use HTTPS (TLS) in front of the app.
- Limit allowed file upload size (app already sets MAX_CONTENT_LENGTH = 10 MB). Ensure the uploads directory is outside any served static directory or configure the server to only serve intended static files.
- Add password reset flows and email verification flows (currently the app stores reset_token/reset_token_expiry but no sending logic).
- Use parameterized queries (this app uses psycopg with parameters — good) and sanitize any unsanitized template inputs when adding rich content.

## Logs & monitoring
- Send stdout/stderr from Gunicorn to a process manager (systemd) or platform logs.
- Add error reporting (Sentry) and health checks / readiness endpoints.

## Contributing
- Create issues and PRs. There is no tests/ directory currently — consider adding unit tests around key features and some integration tests.

## Next steps I can do for you
- Add environment variable support directly in app.py and update instructions.
- Add a Dockerfile and a simple docker-compose.yml with a Postgres service.
- Add a Procfile for Heroku/Render deployment.
- Add a systemd unit example file to the repo in `deploy/`.
- Add Alembic migration scaffolding.

---

If you'd like, I can add a Dockerfile + docker-compose, a Procfile, and a more detailed `deploy/` folder with `nginx` and `systemd` examples — tell me which target platform you'd prefer and I will commit those files.
