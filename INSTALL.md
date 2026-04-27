# Deal Meals - Installation Guide

Swedish grocery deal aggregator with recipe suggestions.

## Quick Install (recommended)

No git clone needed. Just download two files and start:

```bash
mkdir deal-meals && cd deal-meals
wget -O docker-compose.yml https://github.com/ssavant2/deal-meals/releases/latest/download/docker-compose.yml
wget -O .env https://github.com/ssavant2/deal-meals/releases/latest/download/example.env

# Edit .env — set DB_PASSWORD and DB_APP_PASSWORD, also add server IP and/or DNS-name under 'Security'.
docker compose up -d
```

Open `http://[your server IP/DNS-name]:20080` and follow the start guide in the UI.

The UI defaults to Swedish. To switch to English, use the language menu (SV/EN) in the top navigation bar.

To update: `docker compose pull && docker compose up -d`

If a release note says the standalone compose file changed, download the new
`docker-compose.yml` first. When updating from a release that still had the old
idle `app` service, run `docker compose up -d --remove-orphans` once so Docker
removes that retired container.

---

## Developer Install (from source)

For contributing or running a development environment.

### Requirements

- Docker and Docker Compose
- Git
- ~2 GB RAM for a normal install with the bundled container limits.

Large recipe libraries need more memory during cache rebuilds and verified delta
previews. As a conservative sizing rule, budget roughly 1 GiB of web-container
memory per 10,000 active/candidate recipes when rebuilds run in parallel, plus
the database container memory. If you import tens of thousands of recipes,
increase the web memory limit or lower the cache worker caps in `.env`.

### 1. Clone the repository

```bash
git clone https://github.com/ssavant2/deal-meals.git /docker-apps/deal-meals
cd /docker-apps/deal-meals
```

### 2. Configure environment

```bash
cp deploy/example-dev.env .env
```

Edit `.env` and set ALL values marked `CHANGE_ME`:

- `DB_PASSWORD` and `DB_APP_PASSWORD` — choose strong passwords

If accessing from a custom domain, add it to `ALLOWED_HOSTS` (comma-separated).

For a prod-style source install instead of the dev overlay, use:

```bash
cp deploy/example.env .env
```

### 3. Create required directories

```bash
mkdir -p app/logs app/static/recipe_images data certs
```

### 4. Create the database volume

```bash
# Production:
docker volume create deal-meals_postgres_data

# Development (if running dev on the same machine):
docker volume create deal-meals-dev_postgres_data
```

### 5. Build and start

**Production-style source build** (read-only app source mount, no Adminer, no
Python cache):
```bash
docker compose build --no-cache && docker compose up -d
```

**Development source build** (writable app mount, Adminer on port 8071):
```bash
# Dev .env must contain:
#   COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml
#   COMPOSE_PROFILES=dev
docker compose build --no-cache && docker compose up -d
```

The base `docker-compose.yml` is prod-ready. Dev adds `docker-compose.dev.yml` as an overlay (loaded automatically via `COMPOSE_FILE` in `.env`).

First startup takes ~1 minute (database initialization, cache warmup).

### 6. Verify

```bash
# Check all containers are running
docker compose ps

# Check web server logs
docker compose logs web --tail 20

# Open in browser
# Prod: http://localhost:20080
# Dev:  http://localhost:20070
```

### 7. Initial setup (in the web UI)

1. Go to **Butiker** (Stores) tab
2. Select a store location for Willys and/or ICA
3. Go to **Inställningar** (Settings) tab
4. Click **Hämta erbjudanden** (Fetch offers) to scrape current deals
5. Click **Hämta recept** (Fetch recipes) to scrape recipes from enabled sources
6. The system will automatically match recipes to deals

## Architecture

| Container (prod) | Container (dev) | Service | Purpose |
|-------------------|-----------------|---------|---------|
| `deal-meals-web` | `deal-meals-dev-web` | web | FastAPI web server |
| `deal-meals-db` | `deal-meals-dev-db` | db | PostgreSQL database |
| — | `deal-meals-dev-adminer` | adminer | Database admin UI (dev only, port 8071) |

## SSL/HTTPS

The app runs HTTP by default. HTTPS can be enabled via the Settings page in the
web UI — upload your certificate and key there. If SSL causes issues, set
`FORCE_HTTP=true` in `.env` and recreate the web container with
`docker compose up -d web`.

## Authentication (none)

The application has no built-in authentication. It is designed for use on a trusted local network and should not be exposed directly to the internet. Origin validation (CSRF protection) is the only access control.

If you need to expose it externally, add a reverse proxy with an identity provider in front of it — for example Nginx Proxy Manager, Traefik, or Caddy combined with Authentik or a similar authentication solution.

See [Security](docs/SECURITY.md) for the app's threat model and implemented
hardening measures.

## Reverse Proxy (optional)

The app works fine without a reverse proxy. If you put it behind one (Nginx Proxy Manager, Traefik, Caddy, etc.), configure these in `.env`:

1. Add the proxy's hostname/domain to `ALLOWED_HOSTS` so origin validation passes
2. Set `TRUSTED_PROXY` to the proxy's internal IP so rate limiting sees the real client IP

```bash
# Example for Nginx Proxy Manager on Docker bridge network:
ALLOWED_HOSTS=localhost,127.0.0.1,my-domain.example.com
TRUSTED_PROXY=172.18.0.1
```

Find your proxy's IP with: `docker network inspect bridge | grep Gateway`

Then recreate the web container (restart does NOT reload `.env`):
```bash
docker compose up -d web
```

**Without `TRUSTED_PROXY`:** Rate limiting uses the proxy's IP for all requests, meaning all users share one rate limit bucket. This is safe (not bypassable) but less precise.

## What happens on first start

1. **PostgreSQL** starts from the custom DB image and, on an empty volume, runs `database/init.sql` to create all tables
2. **`02-security.sh`** then creates the `deal_meals_app` user with DML-only privileges
3. **Web container** starts FastAPI — no stores or recipes yet
4. **You configure** stores and recipe sources via the UI

## Common commands

```bash
# Rebuild after code changes (--no-cache ensures latest security patches)
docker compose build --no-cache && docker compose up -d

# Restart web only (after editing Python files)
docker compose restart web

# Reload .env changes (restart does NOT reload .env!)
docker compose up -d web

# View logs
docker compose logs -f web
docker compose logs -f db

# Stop everything (data preserved in volume)
docker compose down

# Stop + delete database (WARNING: deletes all data!)
docker compose down -v
```

## Updating an existing install

**Quick Install users:**
```bash
cd /path/to/deal-meals
docker compose pull                   # Pull latest image
docker compose up -d                  # Restart with new image
```

If release notes mention compose-file changes, re-download `docker-compose.yml`
before restarting. For the release that removes the old idle `app` service, use
`docker compose up -d --remove-orphans` once after replacing the compose file.

**Developer Install users:**
```bash
cd /path/to/deal-meals
git pull                              # Get latest code
docker compose build --no-cache       # Rebuild with latest base image
docker compose up -d                  # Restart with new image
```

No database migrations needed — the schema is managed by `init.sql`
(only runs on empty databases) and the app handles any runtime changes.

## Cache Runtime (advanced)

Normal installs do not need any cache-related `.env` settings. This section is
mostly useful when debugging cache behavior or trying to understand what happens
after an offer refresh.

The app uses one official cache runtime:

- full rebuilds use persistent compiled recipe/offer data plus term indexes
- offer refreshes try verified `delta` first
- if delta cannot be applied cleanly, the app falls back to a normal full
  `compiled` rebuild

Optional overrides for debugging:

- `CACHE_DELTA_ENABLED=false` — disable delta and always do a full compiled rebuild after offer refreshes
- `CACHE_DELTA_SKIP_FULL_PREVIEW_AFTER_PROBATION=false` — keep delta on the slower full-preview verification path even after probation is green
- `CACHE_DELTA_PROBATION_MIN_READY_STREAK=10` — minimum consecutive ready probation runs before fast delta is allowed
- `CACHE_DELTA_PROBATION_MIN_VERSION_READY_RUNS=3` — minimum ready probation runs for the current matcher/compiler versions

Delta is safety-first. It can still fall back to a normal full `compiled`
rebuild if the baseline is stale or parity is not clean.

`CACHE_DELTA_VERIFY_FULL_PREVIEW=true` is the built-in default. The app only
skips that full preview after the probation history says the current version
triple is stable enough.

When delta is enabled, real offer-refresh delta attempts also append compact
runtime entries to the probation history file. That lets the app build its own
readiness signal from actual cache refreshes instead of relying only on manual
dev tooling. In the standalone Docker release this history is stored in the
named `data` volume mounted at `/app/data`; in source installs it is mounted
from `./data`.

Practical rollout behavior:

- a fresh installation with empty probation history typically needs `10` green offer-refresh runs before fast delta unlocks
- a normal upgrade with preserved probation history typically needs only `3` green runs for the new matcher/compiler version triple
- a plain restart on unchanged code does not reset that version-specific counter
- if the probation history file is lost, the app has to build confidence again from scratch

## Dev vs Production

| Feature | Prod | Dev |
|---------|------|-----|
| **Compose files** | `docker-compose.yml` only | `docker-compose.yml` + `docker-compose.dev.yml` |
| **Start command** | `docker compose up -d` | `docker compose up -d` (COMPOSE_FILE in .env loads both) |
| **Container prefix** | `deal-meals-` | `deal-meals-dev-` |
| **Volume name** | `deal-meals_postgres_data` | `deal-meals-dev_postgres_data` |
| **Adminer** | Not included | Included (port 8071) |
| **App volumes** | Read-only | Writable source mount |
| **Python cache** | Disabled | Enabled |

> **Running both on the same machine?** Each environment has its own named volume (external). Volumes must be created manually before first start. The separate names prevent any risk of two PostgreSQL instances touching the same data.

## Troubleshooting

### Container won't start
```bash
docker compose logs web --tail 50
```

### Database connection error
Ensure the database volume exists (`docker volume ls | grep deal-meals`) and that
`DB_PASSWORD` / `DB_APP_PASSWORD` are correct in `.env` (`DATABASE_URL` is built
automatically by docker-compose.yml from these values).

### CSRF / 403 errors on POST requests
Add your domain to `ALLOWED_HOSTS` in `.env`, then recreate:
```bash
docker compose up -d web
```
Note: `docker compose restart web` does NOT reload `.env` changes.

### Permission errors (non-root container)
The containers run as uid 1000. Ensure the project directory is owned by your user:
```bash
chown -R $(id -u):$(id -g) app/logs app/static/recipe_images data certs
```
