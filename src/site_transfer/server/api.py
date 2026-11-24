"""Local Studio API; no browser execution or GitHub publishing in PR-02."""
from uuid import UUID, uuid4

import psycopg
import redis
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from site_transfer.config import ConfigError, validate_config
from site_transfer.documentation import initialize_project
from . import db
from .settings import project_root, redis_url

app = FastAPI(title="Site Transfer Studio", version="0.2.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])


@app.middleware("http")
async def local_write_guard(request: Request, call_next):
    # Browser-originated writes must be same-origin. Non-browser clients may omit Origin.
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin is not None and origin != f"{request.url.scheme}://{request.headers.get('host', '')}":
            return JSONResponse(status_code=403, content={"detail": "Cross-origin write denied"})
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse(status_code=403, content={"detail": "Cross-site write denied"})
    return await call_next(request)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    checks = {"database": False, "redis": False}
    try:
        checks["database"] = db.ready()
    except psycopg.Error:
        pass
    try:
        with redis.Redis.from_url(redis_url(), socket_connect_timeout=2, socket_timeout=2) as client:
            checks["redis"] = bool(client.ping())
    except (redis.RedisError, OSError):
        pass
    healthy = all(checks.values())
    return JSONResponse(status_code=200 if healthy else 503,
                        content={"status": "ready" if healthy else "unavailable", "checks": checks})


@app.post("/api/v1/config/validate")
def validate(payload: dict = Body(...)):
    try:
        validate_config(payload)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"valid": True}


@app.get("/api/v1/projects")
def projects(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return {"items": db.list_projects(limit, offset), "limit": limit, "offset": offset}


@app.get("/api/v1/projects/{project_id}")
def project(project_id: UUID):
    item = db.get_project(project_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return item


@app.post("/api/v1/projects", status_code=201)
def create(payload: dict = Body(...)):
    try:
        config = validate_config(payload)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    project_id = uuid4()
    output = project_root() / str(project_id)
    # Generate mandatory documents before committing project metadata.
    # On database failure, leave evidence intact for manual recovery; never
    # delete a potentially committed project's files on an uncertain outcome.
    try:
        initialize_project(config, output)
        return db.create_project(project_id, config)
    except (OSError, ValueError, psycopg.Error) as exc:
        raise HTTPException(status_code=503, detail=f"Project initialization failed; recovery ID: {project_id}") from exc
