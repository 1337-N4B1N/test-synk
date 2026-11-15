# CI/CD Security Demo

A small, deliberately-flawed app used to learn one thing properly: **a CI
pipeline that scans dependencies and code on every push and blocks the merge
when it finds a known CVE.**

The app itself is not the point. The gate is.

- **Backend:** Django 5.1 + Django REST Framework + MySQL
- **Frontend:** Next.js 14 (App Router)
- **CI:** GitHub Actions running **SCA** (`pip-audit`, `npm audit`, `Snyk`),
  **SAST** (`bandit`), with a branch ruleset that blocks the merge

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
| `PyYAML==5.3.1` (CVE-2020-14343) | `backend/requirements.txt:16` | `pip-audit` **and** `Snyk` (SCA) |
| `yaml.load()` on user input | `backend/submissions/views.py:69` | `bandit` — **see the caveat below** |
| `axios@0.21.0` (SSRF / ReDoS / prototype pollution) | `frontend/package.json` | `npm audit` **and** `Snyk` (SCA) |

> **Important mental model:** the scanners read your **pinned dependency
> versions** and your **source code**. They do not read your `import`
> statements, and you do not query NVD or exploit-db by hand. These tools sync
> those databases for you.

### Why two SCA tools?

`pip-audit`/`npm audit` use open advisory databases (PyPI/OSV, GitHub Advisory)
and are free and fast. Snyk uses its own curated database and resolves the full
transitive tree, which is why it found **17 issues in the backend and 31 in the
frontend** where `pip-audit` reported 34 advisories across 5 packages.

Running both is deliberate, not redundant:

- **Free scanners = fast feedback.** No token, no quota, works in any fork.
- **Snyk = the commercial cross-check.** Higher recall, plus fix PRs later.
- **Disagreement is the signal.** A package both agree on is a real problem; one
  only Snyk sees is worth a manual look (Snyk's DB sometimes includes advisories
  not yet in OSV).

The gate fails if **either** finds something at `high` or above — the union, not
the intersection. That's the conservative choice: you don't get to ship because
one scanner missed it.

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
> The bare root `http://localhost:8000/` is also 404 — use `/admin/` for the UI.

Create an admin account to browse stored submissions (and their uploaded CVs).
A fresh clone has no users, so log in as `admin` / `admin` — at the
`Bypass password validation and create user anyway? [y/N]:` prompt, answer `y`:

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

The `backend/config/settings.py` talks to MySQL, so the backend will not start until a MySQL-compatible server is
reachable. Without one, `migrate` dies with:

```
django.db.utils.OperationalError: (2003, "Can't connect to MySQL server on
'127.0.0.1' ([Errno 111] Connection refused)")
```

On Kali, `mysql` on its own is only the **client**. Installing it does not give
you a server:

```bash
which mysqld mariadbd    # if both are missing, you have no server
```

### Step 1 — Get a MySQL server running

Either install one:

```bash
sudo apt update && sudo apt install -y mariadb-server
sudo service mariadb start        # or: sudo systemctl start mariadb
```

Or run one in Docker (independent of the full Compose stack):

```bash
docker run -d --name demo-mysql \
  -e MYSQL_DATABASE=appdb \
  -e MYSQL_USER=appuser \
  -e MYSQL_PASSWORD=apppass \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -p 3306:3306 mysql:8.4
```

Confirm it is listening:

```bash
ss -lnt | grep 3306
```

### Step 2 — Create the database and user

The values must match `backend/.env`. If you used the Docker command above, this
already exists — skip to Step 3. For a locally installed server:

```bash
sudo mysql <<'SQL'
CREATE DATABASE IF NOT EXISTS appdb CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'appuser'@'localhost' IDENTIFIED BY 'apppass';
GRANT ALL PRIVILEGES ON appdb.* TO 'appuser'@'localhost';
FLUSH PRIVILEGES;
SQL
```

### Step 3 — Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # already correct for the settings above
python manage.py migrate
python manage.py runserver
```

Migrations are committed (`submissions/migrations/0001_initial.py` and
`0002_…`), so you do **not** need `makemigrations`.

Required for the admin (the smoke test below checks `/admin/`) — no default
account exists. Use `admin` / `admin` and answer `y` at the password-validation
bypass prompt:

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
| `Snyk (deps)` | `snyk test … --severity-threshold=high` | ❌ **fails** | 17 open issues in the backend, 31 in the frontend |

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
**Settings → Rules → Rulesets → New branch ruleset** for `main`:

- ✅ **Require a pull request before merging** — this is what stops direct
  pushes to `main`. Without it, `git push origin main` bypasses everything.
- ✅ **Require status checks to pass before merging**
- ✅ **Require branches to be up to date** (`strict_required_status_checks_policy`)
- Select all four checks: `Python deps (pip-audit)`, `Python code (bandit)`,
  `JS deps (npm audit)`, `Snyk (deps)`

**That is "prevent pushing" done properly** — enforced server-side, not on your
laptop.

> **Honest caveat:** GitHub.com has **no `pre-receive` hook**, so *nothing* can
> reject a push mid-transfer. SCA needs the files, and the files only exist after
> the commit. What a ruleset gives you is: **the vulnerable commit can exist on a
> branch, but it can never reach `main`.** Only GitHub Enterprise Server or a
> self-managed GitLab can reject the push itself.

### The Snyk token

The Snyk job reads `secrets.SNYK_TOKEN`, which is already set on this repo. To
create your own:

1. Sign up at [snyk.io](https://snyk.io) (free tier: 5 projects).
2. **Account settings → General → Auth Token** → copy it.
3. GitHub: **Settings → Secrets and variables → Actions → New repository
   secret** → name it `SNYK_TOKEN`.

Without the secret the job fails with an authentication error, not a
vulnerability finding — check the log before assuming it found something.
`Snyk` is one of the four required checks, so **a missing token also blocks the
merge.** That's intentional: a gate you can disable by deleting a secret isn't a
gate.

Free-tier note: 5 projects and a monthly test cap. This repo uses one project
per target (backend, frontend), so you have room — but a large org would need the
Team plan (~$25/dev/month).

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
# Optional, only if you have a Snyk token exported locally:
# snyk test --file=backend/requirements.txt --severity-threshold=high
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

No MySQL server is running. You have the client (`mysql`), not the server.
See [Path B, Step 1](#step-1--get-a-mysql-server-running). Confirm with
`ss -lnt | grep 3306`.

### `Permission denied` writing to `backend/media`

The upload directory is root-owned. `sudo chown -R "$USER":"$USER" backend/media`,
or recreate it with `mkdir -p backend/media`.

### `ImproperlyConfigured: mysqlclient 1.4.3 or newer is required`

`backend/config/__init__.py` calls `pymysql.install_as_MySQLdb()`, which reports
itself as `1.4.6`, so this only appears if that import never ran — check you're
starting Django through `manage.py`.

### `Snyk (deps)` fails but the log says nothing about vulnerabilities

Two different failures look identical from the checks list:

- **Not authenticated** — `SNYK_TOKEN` is missing or expired. Real scans print
  `Tested N dependencies for known issues`. An auth failure prints
  `Authentication error` and never mentions a count.
- **Genuinely vulnerable** — `found N issues`. Exit code 1 is *correct* here;
  that's the gate working.

Read the line right after `Testing (backend/requirements.txt)` to tell them
apart. Also note `snyk/actions/setup@master` tracks a moving branch — pin it to a
tag or SHA for reproducibility.

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
3. **SARIF upload** — push scanner results to the Security tab via
   `github/codeql-action/upload-sarif`. Snyk, `osv-scanner`, and Trivy all emit
   SARIF, so this is the natural next step and makes findings browsable rather
   than log-scrolling.
4. **Dependabot / Renovate** — automate the version churn that makes gates red.
   This is what keeps the gate green *without* lowering its threshold.
5. **Reachability analysis** — `pip-audit`, `npm audit`, and this Snyk setup all
   flag a vulnerable package **present in the tree**. Snyk's commercial tier adds
   reachability (is the vulnerable function actually called?), which is the real
   fix for alert fatigue.
6. **Registry proxy policy** — the only control that prevents *installation*
   rather than merging. Point pip/npm at Nexus or Artifactory and deny versions
   with a CVE above your threshold. Stronger than any hook, because the artifact
   never arrives.
7. **CD** — a deploy job that only runs after the security gate passes.

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
│   └── security.yml             the security gate (4 jobs: pip-audit,
│                                bandit, npm audit, Snyk)
└── README.md
```
