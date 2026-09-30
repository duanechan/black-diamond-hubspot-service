# Black Diamond HubSpot Service

Extracts data from HubSpot CRM through the HubSpot REST API (cursor-based pagination) and feeds it into the Glynac data pipeline. It is the dedicated HubSpot extraction engine, called by the Black Diamond core service, and writes results to MinIO (S3-compatible storage), Kafka, and optionally ClickHouse.

For architecture, deployment (Nomad/Vault) and the full design rationale, see the technical design document (`hubspot-service-technical-design.md`).

## Requirements

- Python 3.13 (see `.python-version`)
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker Desktop (running) for the local dependencies
- A HubSpot Private App access token with the scopes listed in the design document

## Quick start

```powershell
# 1. Install dependencies
uv sync

# 2. Create your local config (never commit .env; *.env is gitignored)
Copy-Item .env.example .env      # macOS/Linux: cp .env.example .env

# 3. Start local dependencies (Postgres, MinIO, Kafka, ClickHouse)
docker compose up -d

# 4. Create the database schema
uv run alembic upgrade head

# 5. Run the service
uv run python -m app.main
```

Then check `http://localhost:5720/api/health/` (note the trailing slash; the app redirects `/api/health` to it).

## Local configuration

Copy `.env.example` to `.env` and edit it. The service validates configuration at startup and exits with a list of problems if anything is wrong.

Rules the validator enforces:

- Any secret still starting with `REPLACE_WITH` is rejected, **even for features that are disabled** (for example `MINIO_ACCESS_KEY` when `MINIO_ENABLED=false`). Replace every placeholder.
- `SECRET_KEY` and both HMAC keys must be at least 32 characters.
- Unknown keys in `.env` are rejected, so only add variables the service declares (see `app/config.py`).

Values that match the local `docker-compose.yml`:

| Variable                                                          | Local value                             | Notes                                                                                                                       |
| ----------------------------------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `DB_HOST`                                                         | `localhost`                             | The app runs on your machine; Postgres publishes 5432. Container names like `postgres` only work inside the Docker network. |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD`                             | `hubspot_dev` / `dev_user` / `dev_pass` | From the `postgres` service.                                                                                                |
| `MINIO_ENDPOINT`                                                  | `localhost:9000`                        |                                                                                                                             |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`                           | `minioadmin` / `minioadmin`             | From the `minio` service.                                                                                                   |
| `MINIO_BUCKET`                                                    | `hubspot-dev`                           | Must already exist (see below).                                                                                             |
| `KAFKA_BOOTSTRAP_SERVERS`                                         | `localhost:9092`                        |                                                                                                                             |
| `CLICKHOUSE_PORT`                                                 | `8123`                                  | The client uses ClickHouse's **HTTP** interface. Port 9000 is MinIO locally, not ClickHouse.                                |
| `CLICKHOUSE_USER` / `CLICKHOUSE_PASSWORD` / `CLICKHOUSE_DATABASE` | `default` / `default` / `hubspot`       | From the `clickhouse` service.                                                                                              |

`HUBSPOT_ACCESS_TOKEN` and `HUBSPOT_PORTAL_ID` come from your HubSpot Private App. The token is validated against HubSpot at startup, so an invalid token stops the service from starting. Treat the token like a password and rotate it if it is ever exposed.

## Database migrations

Schema changes are managed with Alembic. The app no longer creates tables itself at startup, so a fresh database needs a migration before the service will work:

```powershell
uv run alembic upgrade head     # apply all pending migrations
uv run alembic current          # show the applied revision
uv run alembic check            # compare models against the live schema
```

To add a schema change: edit the model, then `uv run alembic revision --autogenerate -m "description"`, and **read the generated file before applying it** — autogenerate is a starting point, not a guarantee.

**If a database already has a `scans` table from before this project used Alembic** (built by the old `Base.metadata.create_all`), don't run `upgrade head` on it — that will fail with "table already exists". Instead, mark the baseline as already applied:

```powershell
uv run alembic stamp head
uv run alembic check   # should report no differences
```

This applies to any environment where the table predates migrations, including staging and prod. Whoever owns the deploy for those environments should confirm this has been done before the first real migration ships there, and decide how `alembic upgrade head` gets run as part of deploy (a Nomad prestart task, a manual step, etc.) — that isn't settled yet.

Migration files live in `migrations/` and must be committed alongside any model change; `alembic.ini` should only ever contain the placeholder connection string, never real credentials.

## Local dependencies

`docker-compose.yml` starts:

| Service      | Image                                 | Ports                      |
| ------------ | ------------------------------------- | -------------------------- |
| `postgres`   | `postgres:18`                         | 5432                       |
| `minio`      | `cgr.dev/chainguard/minio:latest`     | 9000 (API), 9001 (console) |
| `kafka`      | `apache/kafka:latest`                 | 9092                       |
| `clickhouse` | `clickhouse/clickhouse-server:latest` | 8123 (HTTP), 9009          |

Data lives in named Docker volumes. Avoid `docker compose down -v` unless you want to wipe Postgres, MinIO and ClickHouse data — in particular, it deletes the MinIO bucket and you'll need to recreate it (see below).

### MinIO

The community `minio/minio` image is no longer published, so this project uses Chainguard's maintained image (`cgr.dev/chainguard/minio`). Things to know:

- **Bucket must exist, but `docker compose up` creates it for you.** The `minio-init` service waits for MinIO's healthcheck to pass, then runs `mc mb --ignore-existing local/hubspot-dev` and exits (`Exited (0)` in `docker compose ps -a` is expected, not a failure). The app itself does not create buckets — it only checks for `MINIO_BUCKET` at startup and refuses to start if it is missing. If `minio-init` didn't run (e.g. you started `minio` on its own with `docker compose up -d minio`), create the bucket by hand:

    ```
    docker compose exec -e MC_HOST_local=http://minioadmin:minioadmin@localhost:9000 minio mc mb local/hubspot-dev
    ```

    or through the console at `http://localhost:9001` (`minioadmin` / `minioadmin`).

- **Runs as non-root.** A volume created by an older root-owned MinIO container will fail with "file access denied". Remove only the MinIO volume (`docker volume ls`, then `docker volume rm <project>_minio-data`) and start again.
- **The image has no `curl`.** The compose healthcheck uses `mc ready local` with an `MC_HOST_local` environment variable instead.

## Running the tests

```powershell
uv run pytest tests/unit          # no external services needed
uv run pytest tests/integration -rs   # needs the compose stack running
```

Integration tests **skip** (rather than fail) when Postgres, MinIO, Kafka or ClickHouse is not reachable. Use `-rs` to see the skip reasons, and check that the run reports passes rather than skips before trusting it. These tests use their own throwaway tables (`create_all` in the test fixtures) and don't exercise Alembic.

## API

Interactive docs are served by Flask-RESTX at the service root (`http://localhost:5720/`).

| Method | Path                       | Auth                | Purpose                                                                                                  |
| ------ | -------------------------- | ------------------- | -------------------------------------------------------------------------------------------------------- |
| GET    | `/api/health/`             | none                | Dependency health (HubSpot, MinIO, Kafka, ClickHouse); 503 when a required or enabled dependency is down |
| GET    | `/api/key/verify`          | HMAC                | Verify HMAC key                                                                                          |
| POST   | `/api/scan/start`          | HMAC                | Start an extraction scan (202)                                                                           |
| GET    | `/api/scan/list`           | HMAC                | List scans                                                                                               |
| GET    | `/api/scan/statistics`     | HMAC                | Aggregate scan stats                                                                                     |
| GET    | `/api/scan/{id}/status`    | HMAC                | Scan status and progress                                                                                 |
| POST   | `/api/scan/{id}/cancel`    | HMAC                | Cancel a scan                                                                                            |
| POST   | `/api/scan/{id}/resume`    | HMAC                | Resume a failed scan                                                                                     |
| DELETE | `/api/scan/{id}/remove`    | HMAC                | Remove a scan record                                                                                     |
| GET    | `/api/objects/`            | HMAC                | List supported HubSpot objects                                                                           |
| GET    | `/api/batch/info`          | HMAC                | HubSpot portal info and API quota                                                                        |
| POST   | `/api/maintenance/cleanup` | HMAC (engineer key) | Purge old scan records                                                                                   |

`/api/health` (no trailing slash) redirects to `/api/health/` with a 308; call the latter directly, or follow redirects (`curl -L`), to see the real status code.

HubSpot and Kafka are always required for a `healthy` status. MinIO and ClickHouse only count when `MINIO_ENABLED` / `CLICKHOUSE_ENABLED` is `true` — if disabled, the endpoint reports `healthy` regardless of their `*_connected` value, which will still show `false`.

### HMAC authentication

When `HMAC_ENABLED=true`, protected endpoints require two headers:

- `X-Timestamp` - Unix time in seconds; rejected if older than `HMAC_SIGNATURE_MAX_AGE` (default 300 s).
- `X-Signature` - hex-encoded HMAC-SHA256 of the following, joined by newlines:

    ```
    <HTTP method>
    <request path, including query string if any>
    <X-Timestamp value>
    <raw request body>
    ```

The key is `HMAC_SECRET_KEY_CORE`, except for `/api/maintenance/cleanup`, which uses `HMAC_SECRET_KEY_ENGINEER`. With `HMAC_ENABLED=false` (the local default) these checks are skipped.

### Starting a scan

```json
{
    "scan_id": "scan-hs-123",
    "org_id": "glynac-org-001",
    "objects": ["contacts", "companies"],
    "filters": { "last_modified_after": "2026-01-01T00:00:00+00:00" },
    "output_format": "parquet",
    "include_associations": true,
    "destination": {
        "minio_bucket": "hubspot-dev",
        "kafka_publish": true,
        "clickhouse_load": false
    }
}
```

`objects` accepts any of: `contacts`, `companies`, `deals`, `tickets`, `leads`, `owners`, `engagements` (see `app/constants.py` for the exact set and default properties). `filters.last_modified_after` enables incremental extraction. `output_format` is `parquet` (default) or `json`.

## Output

**MinIO** - one object per page, plus one metadata file per object type:

```
{bucket}/{org_id}/{scan_id}/{object}/page_{n}.{parquet|json}
{bucket}/{org_id}/{scan_id}/{object}/_metadata.json
```

Page numbers are not zero-padded (`page_1`, `page_2`, ...).

**Kafka** - records are published to `hs.{object}.{environment}` (for example `hs.contacts.dev`). Topics are created automatically by the local broker; create them explicitly in other environments (see the design document).

## Project layout

```
app/
  main.py          Flask app factory and startup wiring
  config.py        Settings and startup validation
  auth/            HubSpot token validation, HMAC decorator
  clients/         HubSpot API client (pagination, retries, associations)
  services/        Extraction orchestration, normalization/dedup, PII masking
  storage/         MinIO, Kafka and ClickHouse clients
  repositories/    Scan persistence (SQLAlchemy / Postgres)
  models/          Database models
  routes/          Flask-RESTX namespaces
migrations/        Alembic environment and revision files
tests/
  unit/            Fast tests, no external services
  integration/     Tests against the docker-compose stack
```

## Known issues

- Deploy-time ownership of `alembic upgrade head` (and the one-time `stamp head` for pre-existing databases) isn't decided yet for staging/prod — see "Database migrations" above.
- Some settings are declared but not yet used by the code: `MAX_CONCURRENT_SCANS`, `SCAN_TIMEOUT_HOURS`, `HUBSPOT_RATE_LIMIT_RPS`, `LOKI_ENABLED`, `ALLOWED_ORIGINS`, and `BD_CORE_URL`.
- There is no Dockerfile or Nomad job definition in this repository yet.
