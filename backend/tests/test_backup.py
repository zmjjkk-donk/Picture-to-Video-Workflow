import io
import hashlib
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import GeneratedArtifact, GenerationJob


def test_backup_export_download_and_restore_round_trip(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data", agnes_api_key="secret-never-backup")
    client = TestClient(create_app(settings))
    created = client.post("/api/projects", json={"name": "可恢复项目", "description": "备份测试"})
    assert created.status_code == 201
    project_id = created.json()["data"]["id"]

    # V2 intermediate files must travel with the database in a portable backup.
    artifact_path = settings.projects_dir / project_id / "jobs" / "job-a" / "outfits" / "look-01.png"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 48), (220, 80, 100)).save(artifact_path, format="PNG")
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    with client.app.state.session_factory() as session:
        job = GenerationJob(id="job-a", project_id=project_id, provider="agnes", status="failed")
        session.add(job)
        session.flush()
        session.add(GeneratedArtifact(job_id=job.id, kind="outfit_image", slot_index=0, relative_path=str(artifact_path.relative_to(settings.data_dir)).replace("\\", "/"), mime_type="image/png", sha256=digest, file_size=artifact_path.stat().st_size, width=32, height=48))
        session.commit()

    exported = client.post("/api/backups/export")
    assert exported.status_code == 201
    backup = exported.json()["data"]
    assert backup["file_count"] >= 2

    listed = client.get("/api/backups").json()["data"]
    assert len(listed) == 1
    downloaded = client.get(f"/api/backups/{backup['id']}/download")
    assert downloaded.status_code == 200
    assert b"secret-never-backup" not in downloaded.content
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert "manifest.json" in archive.namelist()
        assert "app.db" in archive.namelist()
        assert any(name.endswith("project.json") for name in archive.namelist())
        artifact_name = f"projects/{project_id}/jobs/job-a/outfits/look-01.png"
        assert artifact_name in archive.namelist()
        assert hashlib.sha256(archive.read(artifact_name)).hexdigest() == digest
        manifest = __import__("json").loads(archive.read("manifest.json"))
        assert manifest["version"] == "v2"

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
