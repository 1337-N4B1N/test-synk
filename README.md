# CI/CD Security Demo

A small, deliberately-flawed app used to learn one thing properly: **a CI
pipeline that scans dependencies and code on every push and blocks the merge
when it finds a known CVE.**

The app itself is not the point. The gate is.

- **Backend:** Django 5.1 + Django REST Framework + MySQL
- **Frontend:** Next.js 14 (App Router)
- **CI:** GitHub Actions running `pip-audit`, `bandit`, and `npm audit`

Two nearly identical forms are served. They differ only in the libraries behind
them — one clean, one vulnerable. That difference is invisible in the browser
and obvious to the scanners.

---

## What you are looking at

```
  /saysafe ──▶ Next.js form (native fetch) ──▶ POST /api/saysafe/ ──┐
                                                                    │
  /unsafe  ──▶ Next.js form (axios 0.21.0)  ──▶ POST /api/unsafe/  ──┤
                                                                    ▼
                                                        Django + DRF + MySQL
                                                        (uploads land on disk)
```

Both forms accept the same four fields: `full_name`, `email`, `address`, `cv`
(a file). The only difference is which libraries are in play.

| Route      | Frontend transport | Backend behaviour                             |
|------------|--------------------|-----------------------------------------------|
| `/saysafe` | native `fetch`     | server-side upload validation (extension → size → magic bytes → filename) |
| `/unsafe`  | `axios@0.21.0`     | no upload validation, and calls `yaml.load()` on user input |

## What is "unsafe" about `/unsafe`

| Problem | Where | Caught by |
|---|---|---|
| `PyYAML==5.3.1` (CVE-2020-14343) | `backend/requirements.txt:16` | `pip-audit` (dependency scan) |
| `yaml.load()` on user input | `backend/submissions/views.py:69` | `bandit` — **see the caveat below** |
| `axios@0.21.0` (SSRF / ReDoS / prototype pollution) | `frontend/package.json` | `npm audit` (dependency scan) |

> **Important mental model:** the scanners read your **pinned dependency
> versions** and your **source code**. They do not read your `import`
> statements, and you do not query NVD or exploit-db by hand. These tools sync
> those databases for you.

---

## Prerequisites

Pick **one** of the two paths below. Docker is much easier; the manual path
needs a MySQL server you run yourself.

| | Docker path | Manual path |
|---|---|---|
| Needs | Docker + Compose plugin | Python 3.12+, Node 20, a MySQL/MariaDB server |
| MySQL | provided by Compose | **you must install and start it** |
| Ports | 3000, 8000, 3306 | 3000, 8000, 3306 |

Check what you have:

```bash
docker --version && docker compose version
python3 --version     # 3.12 or newer (the image uses 3.12)
node --version        # 20.x
```

---

## Path A — Docker (recommended)

### One-time: make the Docker socket usable without `sudo`

This is the most common reason `docker compose` fails on a fresh Linux install:

```
permission denied while trying to connect to the Docker daemon socket
at unix:///var/run/docker.sock
```

The daemon is running — your user just isn't in the `docker` group.

```bash
sudo usermod -aG docker "$USER"
newgrp docker          # or log out and back in
docker info            # should now print server info instead of permission denied
```

Do this **before** running Compose. It also prevents the next problem: containers
and `sudo`-run commands leaving root-owned files in your project directory.

### Start the stack

```bash
cd cicd-security-demo
docker compose up --build
```

Three containers start: `db` (MySQL 8.4), `backend`, `frontend`. The backend
waits for MySQL's healthcheck, runs migrations, then serves on `runserver`.

| What | Where |
|---|---|
| Frontend | http://localhost:3000 |
| Endpoints | `POST /api/saysafe/` and `POST /api/unsafe/` |
| Django admin | http://localhost:8000/admin/ |

> `/api/` itself returns 404 — only `saysafe/` and `unsafe/` are registered.

Create an admin account to browse stored submissions (and their uploaded CVs):

```bash
docker compose exec backend python manage.py createsuperuser
```

Stop everything, keeping the database:

```bash
docker compose down
```

Wipe the database **and** uploaded files (both are named volumes):

```bash
docker compose down -v
```

### Notes

- `docker-compose.yml` publishes **3306**, so anything already listening on
  MySQL's port will conflict. Stop a local MySQL first, or change the host side
  of the mapping.
- `backend/` and `frontend/` are bind-mounted into the containers, so edits on
  the host hot-reload. `entrypoint.sh` runs `makemigrations` + `migrate` on
  every start.

---

## Path B — Manual (no Docker)

> **Read this first.** The manual path is only harder for one reason: the
> backend needs a **MySQL server it can reach over TCP on your host**. There is
> **no SQLite fallback** — `backend/config/settings.py` always talks to MySQL.
>
> Two traps bite almost everyone here, and both are fixed below:
> 1. **You have the `mysql` client but no server.** Installing `mysql`/`mariadb`
>    gives you the *client* only. Check:
>    ```bash
>    which mariadbd mysqld   # a server exists only if one of these prints a path
>    ```
> 2. **The Compose database is NOT reachable from a host-run backend.** The
>    `db` container from `docker compose up` lives on Docker's internal network;
>    a Django process on your host cannot reach it on `127.0.0.1:3306`. Do **not**
>    try to reuse the Compose `db` for the manual path — give the manual path its
>    own server, as below.

Without a reachable server, `migrate` dies with:

```
django.db.utils.OperationalError: (2003, "Can't connect to MySQL server on
'127.0.0.1' ([Errno 111] Connection refused)")
```

Pick **one** server option in Step 1, then do Steps 2–5.

### Step 1 — Get a MySQL server listening on the host

**Option 1 (recommended on Kali/Debian) — install MariaDB locally.**
It listens on a real host port, speaks `mysql_native_password` (no extra driver
packages needed), and sidesteps all Docker-networking quirks:

```bash
sudo apt update && sudo apt install -y mariadb-server
sudo service mariadb start        # or: sudo systemctl start mariadb
which mariadbd                    # confirm the SERVER now exists
```

**Option 2 — a standalone Docker MySQL, bound to loopback.**
Note the `127.0.0.1:` prefix on the port — without it, a host-run backend may get
"connection refused" on `127.0.0.1` even while the container is up (Docker can
route published ports in a way that skips loopback). Do **not** run this at the
same time as `docker compose up`; both want port 3306.

```bash
docker run -d --name demo-mysql \
  -e MYSQL_DATABASE=appdb \
  -e MYSQL_USER=appuser \
  -e MYSQL_PASSWORD=apppass \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -p 127.0.0.1:3306:3306 mysql:8.4
```

Confirm — either option — that the port is actually listening on your host:

```bash
ss -lnt | grep 3306          # must print a line; empty = no reachable server
```

### Step 2 — Create the database and user

**Skip this if you used Option 2** — the `mysql:8.4` container already created
`appdb` and `appuser` for you.

For the **locally installed MariaDB** (Option 1), create the user for *both*
`localhost` (unix socket) and `127.0.0.1` (TCP), since Step 3 connects over TCP:

```bash
sudo mariadb <<'SQL'
CREATE DATABASE IF NOT EXISTS appdb CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'appuser'@'localhost'  IDENTIFIED BY 'apppass';
CREATE USER IF NOT EXISTS 'appuser'@'127.0.0.1'  IDENTIFIED BY 'apppass';
GRANT ALL PRIVILEGES ON appdb.* TO 'appuser'@'localhost';
GRANT ALL PRIVILEGES ON appdb.* TO 'appuser'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL
```

Verify you can actually log in over TCP before going further:

```bash
mysql -h127.0.0.1 -P3306 -uappuser -papppass appdb -e "SELECT 1;"
```

If that works, the backend will too. If it says "connection refused", your
server from Step 1 isn't running/reachable — fix that first.

### Step 3 — Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Now **edit `backend/.env` and set the DB host to the TCP loopback address**:

```
DB_HOST=127.0.0.1
```

Use `127.0.0.1`, not `localhost`. With a local MariaDB, `localhost` makes the
client switch to a unix socket, while `127.0.0.1` forces a TCP connection on
port 3306 — which is what matches both server options above. Then:

```bash
python manage.py migrate
python manage.py runserver
```

Migrations are committed (`submissions/migrations/0001_initial.py` and
`0002_…`), so you do **not** need `makemigrations`.

Optional, for the admin:

```bash
python manage.py createsuperuser
```

### Step 4 — Frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Frontend: http://localhost:3000 — API: http://localhost:8000/api/saysafe/ and
http://localhost:8000/api/unsafe/

### Step 5 — Point both at each other

`frontend/.env.local` must contain the API base the browser will call:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000/api
```

`backend/.env` must allow the frontend's origin:

```
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Restart `npm run dev` after changing `.env.local` — `NEXT_PUBLIC_*` values are
inlined at build time.

---

## Smoke test

With both servers up:

```bash
# API reachable? Expect 405 -- the endpoint exists but only accepts POST.
curl -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/saysafe/

# Frontend up?
curl -o /dev/null -w '%{http_code}\n' http://localhost:3000/
```

Nothing on `8000` at all means the backend never started — check its terminal
for the MySQL connection error above.

Then, in the browser, on `/saysafe`:

1. Submit with a real `.pdf` → success, row appears in `/admin/`.
2. Submit with a `.txt` renamed to `.pdf` → **rejected**, because the server
   checks the file's magic bytes, not its name.

On `/unsafe`, upload any file with any extension → **accepted and stored**. That
contrast is the demo: `/unsafe` trusts the browser, and the browser can always be
bypassed (Burp, curl, anything).

To reset stored submissions, including files on disk:

```bash
cd backend && python manage.py reset_submissions
# or non-interactively:
cd backend && python manage.py reset_submissions --no-input
```

---

## The actual lesson: make CI red, then green

### 1. Put it on GitHub

```bash
git init
git add .
git commit -m "Initial CI/CD security demo"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

The `security-gate` workflow runs three jobs on every push and PR.

### 2. What each job actually does today

Measured on 13 Nov 2026 against this repo:

| Job | Command | Result | Why |
|---|---|---|---|
| `Python deps (pip-audit)` | `pip-audit -r backend/requirements.txt --strict` | ❌ **fails** | 34 advisories across `PyYAML`, `Django`, `djangorestframework`, `cryptography`, `python-dotenv` |
| `Python code (bandit)` | `bandit -r backend -ll` | ✅ **passes** | `views.py:69` carries a `# nosec` marker, which suppresses `B506` |
| `JS deps (npm audit)` | `npm audit --audit-level=high` | ❌ **fails** | `axios 0.21.0`, plus `next 14.2.15` and `postcss` |

**The bandit caveat is real and worth understanding.** The `# nosec` in

```python
parsed = yaml.load(raw_meta)  # nosec-intentional-for-demo  # noqa
```

tells bandit to skip that line. Remove the marker and the job goes red with
`B506: yaml_load`. That is a useful thing to learn: **`# nosec` is how a red
gate silently becomes green.** Anyone can silence a scanner; the review question
is always *why* it was silenced.

`pip-audit` also shows that a single planted CVE is not the whole story. Pinned
versions rot. `Django==5.1.4` was current when this repo was written; today it
carries 20 advisories on its own.

### 3. Turn the gate into a real block

A red check only *blocks* a merge if branch protection demands it. On GitHub:
**Settings → Branches → Add branch ruleset** for `main`:

- ✅ Require a pull request before merging
- ✅ Require status checks to pass before merging
- Select `Python deps (pip-audit)`, `Python code (bandit)`, `JS deps (npm audit)`

**That is "prevent pushing" done properly** — enforced server-side, not on your
laptop.

### 4. Make it green

Verified working backend set — `pip-audit` reports no known vulnerabilities:

```text
Django==5.2.17
djangorestframework==3.18.3
django-cors-headers==4.9.0
PyMySQL==1.2.4
cryptography==50.0.2
python-dotenv==1.2.4
gunicorn==27.0.1
PyYAML==6.0.3
```

Also replace `yaml.load(raw_meta)` with `yaml.safe_load(raw_meta)` and drop the
`# nosec`, so the `bandit` job is green **because the code is safe**, not because
the scanner was muted.

Bumping only `PyYAML` to `6.0.2` is **not** enough — `pip-audit` still exits
non-zero on the other four packages. That is the realistic lesson: patching the
one CVE you know about leaves the gate red.

**Frontend is the hard one.** Raising `axios` to `1.x` (tested with `1.7.9`)
clears the axios advisories, but `npm audit` still fails on `next@14.2.15` and
the `postcss` it pulls in — 3 vulnerabilities remained. The only fix
`npm audit` offers is `next@16.x`, a breaking major upgrade (App Router is
stable in 16 and React 18.2+ is still accepted, but config/dev-server details
change and Node ≥ 20.9 is required). Expect the `npm audit` job to stay red until
you take that upgrade deliberately, on its own branch, and re-test both routes.

### 5. (Optional) Local pre-push hook — fast feedback, weaker gate

A git hook runs the scan before the push leaves your machine. Instant feedback,
but bypassable with `git push --no-verify`, so it complements the server-side
gate — it never replaces it.

`.git/hooks/pre-push`, then `chmod +x .git/hooks/pre-push`:

```sh
#!/bin/sh
set -e
pip-audit -r backend/requirements.txt || exit 1
(cd frontend && npm audit --audit-level=high) || exit 1
```

---

## Troubleshooting

These are the failures this project actually produces.

### `permission denied ... /var/run/docker.sock`

Your user is not in the `docker` group. See
[Path A, one-time setup](#path-a--docker-recommended). `sudo docker ...` works
around it, but leaves root-owned files behind — which is the next problem.

### `npm error code EACCES ... mkdir '.../frontend/node_modules/axios'`

`node_modules` or `.next` is owned by `root` (or `nobody`) from an earlier
`sudo docker` / `sudo npm` run. Your own user can't write there.

```bash
cd cicd-security-demo
sudo chown -R "$USER":"$USER" .
rm -rf frontend/node_modules frontend/.next backend/media
```

Then re-run `npm install`. Prefer fixing the `docker` group over using `sudo`.

### `Can't connect to MySQL server on '127.0.0.1' ([Errno 111] Connection refused)`

No MySQL server is reachable on your host's port 3306. Two common causes:

- **You have the client, not a server.** `which mariadbd mysqld` prints nothing.
  Install/start one — see [Path B, Step 1](#step-1--get-a-mysql-server-listening-on-the-host).
- **You're trying to reuse the Compose `db`.** The `db` container from
  `docker compose up` is only reachable *inside* Docker, not from a host-run
  backend — `ss -lnt | grep 3306` prints nothing on the host even though the
  container is healthy. Give the manual path its own server (Path B, Step 1),
  or just use the all-Docker Path A instead.

Confirm a server is actually listening with `ss -lnt | grep 3306` before
retrying `migrate`.

### `Permission denied` writing to `backend/media`

The upload directory is root-owned. `sudo chown -R "$USER":"$USER" backend/media`,
or recreate it with `mkdir -p backend/media`.

### `ImproperlyConfigured: mysqlclient 1.4.3 or newer is required`

`backend/config/__init__.py` calls `pymysql.install_as_MySQLdb()`, which reports
itself as `1.4.6`, so this only appears if that import never ran — check you're
starting Django through `manage.py`.

### Frontend loads but submissions fail

Open the browser console. A CORS error means `CORS_ALLOWED_ORIGINS` doesn't
include the origin you're browsing from. A connection error means
`NEXT_PUBLIC_API_BASE` is wrong — remember it is baked in at build time, so
restart the dev server.

### Port 3306 already in use

Something else owns MySQL's port. Stop it, or remap the host side in
`docker-compose.yml` (`"13306:3306"`) and update `DB_PORT` in `backend/.env`.

---

## Where to go next

1. **Caching** — cache pip/npm installs in the workflow.
2. **A build/test job** — real Django tests and `next build` as additional
   required checks.
3. **Aggregate scanner** — add Google's `osv-scanner` or Trivy, which cover many
   ecosystems in one tool.
4. **SARIF upload** — push results to the Security tab via
   `github/codeql-action/upload-sarif`.
5. **Dependabot / Renovate** — automate the version churn that makes gates red.
6. **CD** — a deploy job that only runs after the security gate passes.

## Project layout

```
cicd-security-demo/
├── backend/
│   ├── config/                  settings, urls, PyMySQL shim
│   ├── submissions/             Submission model, serializers, the two endpoints
│   │   └── migrations/          committed — no makemigrations needed
│   ├── media/                   uploaded CVs (created on demand)
│   ├── entrypoint.sh            wait for MySQL → migrate → runserver
│   ├── requirements.txt         includes the deliberately old PyYAML
│   └── Dockerfile
├── frontend/
│   ├── app/                     / , /saysafe , /unsafe
│   ├── components/              SubmissionForm.js (shared by both routes)
│   ├── package.json             includes the deliberately old axios
│   └── Dockerfile
├── docker-compose.yml           mysql + backend + frontend
├── .github/workflows/
│   └── security.yml             the security gate (3 jobs)
└── README.md
```
