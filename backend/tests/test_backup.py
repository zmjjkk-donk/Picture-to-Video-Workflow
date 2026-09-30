import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_backup_export_download_and_restore_round_trip(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    created = client.post("/api/projects", json={"name": "可恢复项目", "description": "备份测试"})
    assert created.status_code == 201
    project_id = created.json()["data"]["id"]

    exported = client.post("/api/backups/export")
    assert exported.status_code == 201
    backup = exported.json()["data"]
    assert backup["file_count"] >= 2

    listed = client.get("/api/backups").json()["data"]
    assert len(listed) == 1
    downloaded = client.get(f"/api/backups/{backup['id']}/download")
    assert downloaded.status_code == 200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert "manifest.json" in archive.namelist()
        assert "app.db" in archive.namelist()
        assert any(name.endswith("project.json") for name in archive.namelist())

    assert client.delete(f"/api/projects/{project_id}").status_code == 200
    assert client.get(f"/api/projects/{project_id}").status_code == 404

    restored = client.post(f"/api/backups/{backup['id']}/restore?mode=replace")
    assert restored.status_code == 200
    project = client.get(f"/api/projects/{project_id}")
    assert project.status_code == 200
    assert project.json()["data"]["name"] == "可恢复项目"


def test_backup_import_rejects_invalid_zip(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    response = client.post("/api/backups/import", files={"file": ("bad.zip", b"not a zip", "application/zip")})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "BACKUP_INVALID"
