# Open questions

Things in this repo that are implemented but not yet signed off by their owner. These are not bugs but decisions someone else needs to make.

## 1. Staging/prod migration ownership

`nomad/{stage,prod}/black-diamond-hubspot-service.hcl` run `alembic upgrade head` as a prestart task on every deploy (see `README.md` → "Database migrations"). Before this runs for real:

- Confirm whether staging/prod already have a `scans` table from the old `create_all()`. If so, run `alembic stamp head` there once, or the first deploy will fail with "table already exists".
- The `migrate` task currently gets the same full Vault secret set as the main app task (because `alembic/env.py` calls `validate_settings()`, which requires everything). Decide if that's acceptable or if it should be narrowed to just `DB_*`.

**Owner:** whoever owns Nomad/Vault for this service.

## 2. `BD_CORE_URL`

Is core expecting a callback? The design doc says this service should `PATCH /scans/{scan_id}` back to Black Diamond core when a scan completes. The code never reads `BD_CORE_URL` or makes that call. Needs an answer before anyone touches it:

- If core expects the callback, implement it.
- If core polls `/api/scan/{id}/status` instead, remove `BD_CORE_URL` and fix the design doc.

**Owner:** whoever owns the Black Diamond core service.

## 3. Other unused settings

`MAX_CONCURRENT_SCANS`, `SCAN_TIMEOUT_HOURS`, `HUBSPOT_RATE_LIMIT_RPS`, `LOKI_ENABLED`, `ALLOWED_ORIGINS` are declared in `app/config.py` and validated at startup, but nothing in the code reads them yet. Each is a small, separate feature (a scan concurrency limit, a timeout, a rate limiter, log shipping, CORS) and it's worth deciding one at a time whether it's still planned or should be removed.

**Owner:** whoever's picking up the next chunk of work on this service.
