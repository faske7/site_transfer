"""API contract tests without a live database; Compose smoke test is separate."""
from uuid import UUID

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg")
pytest.importorskip("redis")

from fastapi.testclient import TestClient
from site_transfer.server import api


@pytest.fixture
def client():
    return TestClient(api.app, base_url="http://localhost")


@pytest.fixture
def config():
    return {"source": {"url": "https://example.com"}, "target": {"project_name": "demo"}}


def test_live(client):
    assert client.get("/health/live").json() == {"status": "ok"}


def test_bad_host():
    with TestClient(api.app, base_url="http://evil.example") as client:
        assert client.get("/health/live").status_code == 400


def test_cross_origin_denied(client, config):
    response = client.post("/api/v1/projects", json=config, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_validate(client, config):
    assert client.post("/api/v1/config/validate", json=config).json() == {"valid": True}
    assert client.post("/api/v1/config/validate", json={}).status_code == 422


def test_create_project(client, config, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "project_root", lambda: tmp_path)

    def save(project_id, data):
        assert (tmp_path / str(project_id) / "CONTEXT.md").is_file()
        assert (tmp_path / str(project_id) / "AGENTS.md").is_file()
        return {"id": project_id, "config": data}

    monkeypatch.setattr(api.db, "create_project", save)
    response = client.post("/api/v1/projects", json=config, headers={"Origin": "http://localhost"})
    assert response.status_code == 201
    UUID(response.json()["id"])
    assert response.json()["config"] == config


def test_list_and_read(client, monkeypatch):
    monkeypatch.setattr(api.db, "list_projects", lambda limit, offset: [])
    monkeypatch.setattr(api.db, "get_project", lambda project_id: None)
    assert client.get("/api/v1/projects").json()["items"] == []
    assert client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/v1/projects?limit=101").status_code == 422
