# Sadak Saathi Backend

## Overview
Backend service for Sadak Saathi using FastAPI, PostgreSQL (PostGIS), Redis, and Docker.

## Getting Started

### 1. Prerequisites
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/) installed.

### 2. Running the Services

1. Clone this repo
2. Run:

```
docker-compose up --build
```

- This starts backend (FastAPI), PostGIS DB, and Redis.

### 3. Health Check

- Once running, check health endpoint:

```
curl http://localhost:8000/health
```
Expected output:
```
{"status": "ok"}
```

## Environment Variables

### NeonDB (Cloud PostgreSQL)
To use NeonDB for your backend database, set the environment variable `NEONDB_URL` in your `.env` file (or export it before running).

Example `.env` entry:
```
NEONDB_URL='postgresql://neondb_owner:***REMOVED***@ep-autumn-cherry-a18ij12x-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
```

If `NEONDB_URL` is set, the backend will use it automatically. Otherwise, local PostGIS settings from docker-compose or individual environment variables are used.

### Redis
Defaults are set for Redis in `docker-compose.yml`, but can be overridden with `REDIS_HOST` and `REDIS_PORT` in `.env`.

(See app/db/database.py for all supported variables.)


## Project Structure

- `app/main.py` : FastAPI app entrypoint
- `app/api/routing.py` : API endpoints
- `app/db/database.py` : DB & Redis config
- `requirements.txt` : Python dependencies
- `docker-compose.yml` : Container definitions

## Database Migrations

### Spatial Index Migration

To ensure fast geospatial queries, you **must** add spatial indexes on the `location` fields:

**How to run the migration:**

```
cd app/db
python migrate_spatial_index.py
```

This will add (if missing) spatial indexes on both `hazards.location` and `hazard_reports.location`.

---

## Next Steps
- Implement more endpoints and services in app/api and app/services
- Add DB models in app/models

---

## Security: NeonDB Credential Rotation

**It is critical to rotate your NeonDB credentials periodically and IMMEDIATELY if any secrets are ever exposed.**

**How to rotate your NeonDB DB credentials:**
1. Log in to your [Neon Console](https://console.neon.tech/).
2. Select your project/database.
3. Navigate to the 'Settings' or 'Connection' tab.
4. Rotate (change/reset) your DB password/user, copy the new `postgresql://` connection string.
5. Update your new secret in your deployment host/CI/.env (never commit the secret itself).
6. Redeploy/restart the backend services (locally and in production) with the new secret.
7. Remove any previously-leaked secrets from all possible locations and invalidate them.

**NEVER commit DB credentials, even to private repos. Use environment variables via `.env` or CI secret stores.**

