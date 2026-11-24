# Local Docker runtime

Requirements: Docker Engine with Compose v2 (Docker Desktop is sufficient), native arm64 on Apple Silicon. No host Docker socket is mounted. API is loopback-only; do not expose it remotely without authentication and transport security.

```sh
cp .env.example .env
# Edit .env: choose a unique POSTGRES_PASSWORD before the first startup.
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
curl -fsS http://localhost:8080/health/live
curl -fsS http://localhost:8080/health/ready
open http://localhost:8080/docs
```

PR-03 builds and serves the React GUI at http://localhost:8080/. Swagger remains at /docs.
Use the example configuration to create a project:

```sh
curl -fsS -H 'Content-Type: application/json' \
  --data-binary @examples/remaxdelux.json http://localhost:8080/api/v1/projects
curl -fsS http://localhost:8080/api/v1/projects
```

Run unit tests locally with `python -m pip install -e '.[dev,server]'` and `python -m pytest -v`.
Verify Compose on Apple Silicon and restart persistence before merge.

Stop with `docker compose down` (no -v). Named volumes preserve metadata, Redis and project documents. Do not use down -v unless intentionally deleting data. Project files are initially stored in the projects volume; export and native folder integration come later. A failed metadata commit may leave an orphaned project directory; use the returned recovery ID to inspect it. Automated reconciliation is deferred. Readiness covers PostgreSQL and Redis, not worker execution. Capture is not implemented.

The API assumes a trusted single-user host; loopback and browser-origin checks are not full authentication. Docker images and dependencies use version ranges; a reproducible lock/digest policy is deferred.
