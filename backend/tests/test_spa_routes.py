from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(data_dir=tmp_path / "data"))) as test_client:
        yield test_client


@pytest.mark.parametrize("path", [
    "/dashboard", "/projects", "/projects/new",
    "/projects/11111111-1111-1111-1111-111111111111",
    "/jobs/11111111-1111-1111-1111-111111111111",
    "/history", "/assets", "/backups", "/settings",
])
def test_frontend_document_routes_can_be_refreshed(client, path):
    response = client.get(path, headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AI Outfit Studio" in response.text
    assert response.text == client.get("/").text


@pytest.mark.parametrize("path", [
    "/api/does-not-exist", "/assets/missing.js", "/assets/missing.css",
    "/projects/missing.png", "/.env", "/unrelated", "/%2e%2e/.env",
])
def test_missing_api_files_and_unrelated_routes_do_not_return_spa(client, path):
    response = client.get(path, headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "AI Outfit Studio" not in response.text


def test_head_supports_frontend_documents_but_post_is_not_rewritten(client):
    response = client.head("/projects/new")
    assert response.status_code == 200
    assert response.content == b""
    assert int(response.headers["content-length"]) > 0
    assert client.post("/dashboard").status_code == 405
    assert client.get("/api/health").json()["database"] == "ok"


def test_backend_without_frontend_build_keeps_api_working(tmp_path: Path):
    with TestClient(create_app(Settings(project_root=tmp_path, data_dir=tmp_path / "data"))) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/dashboard").status_code == 404
