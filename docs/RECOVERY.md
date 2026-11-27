# PR-10 — Job lifecycle and recovery

## Upgrade
Stop old API and worker before migrating to schema 4; do not delete volumes. Finish active jobs first. The additive migration retires legacy queued/running rows and building kits, preserves files and completed runs, creates event snapshots, and never replays a legacy capture UUID. Use `docker compose stop api worker` then `docker compose up -d --build --wait`. Rebuild desktop separately to bundle the same commit; an older desktop bundle can start obsolete code and must not be used against schema 4.

## Lifecycle contract
PostgreSQL is authoritative. API writes durable queued/pending intents. API lifespan dispatcher reconciles every 5 seconds, claims at most 20 expired rows and reserves at most 10 due deliveries using row locks and SKIP LOCKED. Redis delivery is at least once; claims are conditional. Up to 12 reservations per stage, 300 seconds apart; after exhaustion the job becomes failed. Dispatch pauses when worker registry heartbeat is stale. If worker remains absent indefinitely, undispatched queued intents remain queued and can be cancelled. Worker parent reports heartbeat every ~15 seconds; API readiness requires a heartbeat newer than 90 seconds (liveness signal, not a proof of free capacity). API must run for reconciliation. No extra Compose service.

Capture claim has random ownership token, absolute 5550-second lease (90-minute soft task limit, hard task limit 5430 + 120-second grace), progress heartbeat at committed manifest boundaries. Expired running capture is marked failed; recorded evidence and files retained, not promoted to completed/partial because filesystem consistency cannot be proved. Manual authorized retry uses a new UUID and unique retry parent, max 3 capture attempts per chain. No automatic website recapture. New manually started chains are separate. Cancellation is cooperative at viewport boundaries, wins over a concurrent terminal write if committed first, and preserves recorded artifacts without allowing pipeline export from failed captures.

Kit tasks have 390-second lease (hard limit 330 + grace); interrupted kit auto-requeues at most 3 attempts, validation/ordinary errors require manual retry within budget. Each attempt writes a unique token-scoped ZIP; only current owner may commit its hash/path. Old ready ZIP paths still work. No automatic deletion of orphan files. Capture completion and kit execution are separate tasks. Cancelled kit cannot publish a ready pointer; already completed reference capture remains usable for direct export. Cancellation is not a process kill.

Lifecycle events are transactional snapshots on status/attempt/dispatch/cancel/error changes, latest 100 exposed per capture. No raw Celery log streaming or per-route resume. Progress heartbeat is not an independent capture thread and does not extend the hard deadline. A fenced old process may still leave orphan files in its own failed run directory, but cannot publish a result or overwrite a retry's run. No schema downgrade support.

## Tests
Run ordinary pytest and opt-in PostgreSQL integration tests against a disposable database:

```bash
docker run --rm -d --name site-transfer-test-pg -e POSTGRES_PASSWORD=local-test-only -p 127.0.0.1:55432:5432 postgres:17-alpine
docker exec site-transfer-test-pg pg_isready -U postgres
SITE_TRANSFER_TEST_POSTGRES_DSN='postgresql://postgres:local-test-only@127.0.0.1:55432/postgres' python -m pytest -v
docker stop site-transfer-test-pg
```

The tests create and drop a random isolated schema; do not point at production. Smoke: new pipeline, cancel queued/running, manually retry failed job, compare IDs and old screenshot hashes, verify worker readiness changes after worker stop/start. Simulate a killed worker and inspect lease expiry and events (production capture/kit leases are 5550/390 seconds); integration tests accelerate expiry by modifying only disposable test rows. Test broker-loss by stopping Redis on a disposable runtime only. No destructive fault injection against existing projects.

PR-18: Capture soft/hard/lease deadlines share constants in server/settings.py. The extended 90-minute budget applies to new claims only; existing expired or running jobs are not renewed. Worker liveness and kit limits are unchanged. A dead capture owner can now take longer to reconcile; no automatic recapture or indefinite renewal is introduced.
