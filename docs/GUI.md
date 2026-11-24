# Site Transfer Studio GUI

Use the existing .env and volumes. From the repository root:

```sh
docker compose up -d --build --wait
open http://localhost:8080
```

The React/TypeScript interface is compiled in a Node 22 multi-stage image and served by FastAPI at the same loopback origin. Swagger remains at /docs. If SITE_TRANSFER_PORT differs from 8080, open the configured port. No host Node install is needed for Docker.

## Local frontend development

With the API running on port 8080:

```sh
cd frontend
npm install
npm run test
npm run build
npm run dev
```

Open http://127.0.0.1:5173. The dev proxy preserves the incoming Host header so the API's same-origin write checks work. Production does not require CORS.

## Acceptance checks

- Dashboard reflects database/Redis readiness and registry results.
- Create a project manually, validate invalid config, import the example JSON, and inspect the saved project.
- Existing projects survive container recreation; API and Swagger still work.
- Inspect narrow and wide browser layouts and verify no capture job is claimed.
- Run Python tests plus frontend tests and production build on ARM64.

PR-03 contains no capture/analysis/compare/publish jobs. Health does not prove worker readiness. The project file list is the documented scaffold contract, not a live file browser. Desktop native transport is deferred to PR-09. Dependency lockfile generation is pending local npm verification; direct dependencies are pinned.
