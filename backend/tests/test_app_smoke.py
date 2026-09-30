from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_app_smoke_health_and_system_info(tmp_path: Path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    info = client.get("/api/system/info")
    assert info.status_code == 200
    assert info.json()["data"]["mode"] == "mock"
