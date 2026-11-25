"""Local Studio API; no browser execution or GitHub publishing in PR-02."""
import os
from tempfile import NamedTemporaryFile
from starlette.background import BackgroundTask
from site_transfer.manifest import build_kit, evidence_file
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import redis
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from site_transfer.config import ConfigError, validate_config
from site_transfer.documentation import initialize_project
from . import db, jobs, comparisons
from threading import Lock
from pydantic import BaseModel
from .storage import screenshot_path, design_path, run_root
from .worker import run_capture, run_kit
from site_transfer.manifest import digest
from .settings import project_root, redis_url

app = FastAPI(title="Site Transfer Studio", version="0.8.0")
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

@app.post("/api/v1/projects/{project_id}/captures", status_code=202)
def start_capture(project_id: UUID, payload: dict = Body(...)):
    if payload not in ({"authorized": True}, {"authorized": True, "pipeline": True}):
        raise HTTPException(status_code=422, detail="Confirm authorization to capture the reference")
    if db.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    job_id = uuid4()
    try:
        item = jobs.create(job_id, project_id, pipeline=payload.get('pipeline', False))
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="A capture is already active") from exc
    try:
        run_capture.apply_async(args=[str(job_id)], task_id=str(job_id), retry=False)
    except Exception as exc:
        jobs.finish(job_id, "failed", "Queue dispatch failed", expected="queued")
        raise HTTPException(status_code=503, detail="Could not dispatch capture") from exc
    return item


@app.get("/api/v1/projects/{project_id}/captures")
def captures(project_id: UUID):
    if db.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"items": jobs.list_jobs(project_id)}


@app.get("/api/v1/projects/{project_id}/captures/{job_id}/screenshots/{index}")
def screenshot(project_id: UUID, job_id: UUID, index: int):
    job = jobs.get(project_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    try:
        path = screenshot_path(project_id, job_id, job["manifest"], index)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Screenshot not found") from exc
    return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})


def _design_response(project_id, job_id, index=None):
    job = jobs.get(project_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    try:
        path = design_path(project_id, job_id, job["manifest"], index)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Design evidence not found") from exc
    return FileResponse(path, media_type="application/json", headers={"X-Content-Type-Options":"nosniff"})


@app.get("/api/v1/projects/{project_id}/captures/{job_id}/design/{index}")
def design_report(project_id: UUID, job_id: UUID, index: int):
    return _design_response(project_id, job_id, index)


@app.get("/api/v1/projects/{project_id}/captures/{job_id}/design-tokens")
def design_tokens(project_id: UUID, job_id: UUID):
    return _design_response(project_id, job_id)


@app.get("/api/v1/projects/{project_id}/captures/{job_id}/assets")
def asset_manifest(project_id: UUID, job_id: UUID):
    job = jobs.get(project_id, job_id)
    if job is None or job["manifest"].get("asset_manifest") != "asset-manifest.json":
        raise HTTPException(status_code=404, detail="Asset inventory unavailable")
    try:
        path = evidence_file(run_root(project_id, job_id), "asset-manifest.json")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Asset inventory missing") from exc
    return FileResponse(path, media_type="application/json", headers={"X-Content-Type-Options":"nosniff"})


@app.get("/api/v1/projects/{project_id}/captures/{job_id}/reference-kit")
def reference_kit(project_id: UUID, job_id: UUID):
    job = jobs.get(project_id, job_id)
    project = db.get_project(project_id)
    if job is None or project is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    if job["status"] not in ("completed", "partial"):
        raise HTTPException(status_code=409, detail="Select a completed or partial capture")
    with NamedTemporaryFile(suffix=".zip", delete=False) as handle:
        path = Path(handle.name)
    try:
        build_kit(project["config"], job, run_root(project_id, job_id), path)
    except (ValueError, OSError, KeyError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Reference kit unavailable: " + str(exc)[:200]) from exc
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return FileResponse(path, media_type="application/zip", filename=f"reference-kit-{job_id}.zip",
                        headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"},
                        background=BackgroundTask(path.unlink, missing_ok=True))


class ComparisonRequest(BaseModel):
    reference_run: UUID
    implementation_project: UUID
    implementation_run: UUID


comparison_lock = Lock()


@app.post("/api/v1/projects/{project_id}/comparisons", status_code=201)
def create_comparison(project_id: UUID, payload: ComparisonRequest):
    if not comparison_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Another comparison is in progress")
    try:
        return comparisons.create(project_id,payload.reference_run,payload.implementation_project,payload.implementation_run)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404,detail="Capture not found") from exc
    except (ValueError,OSError,KeyError) as exc:
        raise HTTPException(status_code=422,detail=str(exc)[:250]) from exc
    finally:
        comparison_lock.release()


@app.get("/api/v1/projects/{project_id}/comparisons")
def list_comparisons(project_id: UUID):
    return {"items":comparisons.list_results(project_id)}


@app.get("/api/v1/projects/{project_id}/comparisons/{comparison_id}")
def comparison_report(project_id: UUID, comparison_id: UUID):
    try:
        return comparisons.read(project_id,comparison_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404,detail="Comparison not found") from exc


@app.get("/api/v1/projects/{project_id}/comparisons/{comparison_id}/diff/{index}")
def comparison_diff(project_id: UUID, comparison_id: UUID, index: int):
    try:
        path=comparisons.diff_path(project_id,comparison_id,index)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404,detail="Diff not found") from exc
    return FileResponse(path,media_type="image/png",headers={"X-Content-Type-Options":"nosniff"})


@app.post("/api/v1/projects/{project_id}/captures/{job_id}/cancel")
def cancel_capture(project_id: UUID, job_id: UUID):
    item=jobs.request_cancel(project_id,job_id)
    if item is None:
        raise HTTPException(status_code=409,detail="Capture is not active")
    return item


@app.post("/api/v1/projects/{project_id}/captures/{job_id}/build-kit",status_code=202)
def retry_kit(project_id: UUID, job_id: UUID):
    item=jobs.get(project_id,job_id)
    if item is None:
        raise HTTPException(status_code=404,detail="Capture not found")
    if item["status"] not in ("completed","partial") or item["cancel_requested"] or item["kit_status"] not in ("pending","failed","not_requested"):
        raise HTTPException(status_code=409,detail="Kit cannot be built in current state")
    try:
        run_kit.apply_async(args=[str(project_id),str(job_id)],retry=False)
    except Exception as exc:
        raise HTTPException(status_code=503,detail="Kit dispatch failed") from exc
    return {"status":"submitted"}


@app.get("/api/v1/projects/{project_id}/captures/{job_id}/pipeline-kit")
def pipeline_kit(project_id: UUID, job_id: UUID):
    item=jobs.get(project_id,job_id)
    if item is None or item["kit_status"]!="ready":
        raise HTTPException(status_code=404,detail="Pipeline kit unavailable")
    try:
        path=evidence_file(run_root(project_id,job_id),"reference-kit.zip")
        if digest(path)!=item["kit_info"].get("sha256"):
            raise ValueError("Checksum mismatch")
    except (ValueError,OSError) as exc:
        raise HTTPException(status_code=409,detail="Kit integrity check failed") from exc
    return FileResponse(path,media_type="application/zip",filename=f"reference-kit-{job_id}.zip",
                        headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


# The production UI is served by the API on the same origin. No catch-all route
# can shadow API/health endpoints. The initial frontend uses in-memory navigation.
ui_dir = Path(os.environ.get("STUDIO_UI_DIR", "/app/studio-ui"))
if (ui_dir / "index.html").is_file() and (ui_dir / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=ui_dir / "assets"), name="studio-assets")

    @app.get("/", include_in_schema=False)
    def studio():
        return FileResponse(ui_dir / "index.html", headers={"Cache-Control": "no-cache"})
