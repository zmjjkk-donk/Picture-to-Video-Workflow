from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.test_api_projects_assets import create_project, image_bytes


def test_relative_data_dir_is_fixed_at_settings_creation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(data_dir=Path("data"))
    assert settings.data_dir == tmp_path / "data"
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    assert settings.database_path == tmp_path / "data" / "app.db"


def test_relative_data_dir_upload_persists_and_can_generate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(data_dir=Path("data"))
    with TestClient(create_app(settings)) as client:
        project_id = create_project(client)
        model = client.post(
            f"/api/projects/{project_id}/assets/model",
            files={"file": ("model.png", image_bytes((10, 20, 30)), "image/png")},
        )
        assert model.status_code == 201
        model_data = model.json()["data"]
        assert not Path(model_data["stored_path"]).is_absolute()
        assert (settings.data_dir / model_data["stored_path"]).is_file()
        clothing_ids = []
        for slot in range(3):
            response = client.post(
                f"/api/projects/{project_id}/assets/clothing",
                data={"name": f"服装{slot + 1}", "slot_index": str(slot)},
                files={"file": (f"look{slot}.png", image_bytes((slot * 60, 80, 120)), "image/png")},
            )
            assert response.status_code == 201
            clothing_ids.append(response.json()["data"]["id"])
        assert client.get(f"/api/projects/{project_id}").json()["data"]["status"] == "ready"
    client.app.state.engine.dispose()

    # A fresh application must read the same database and saved files.
    with TestClient(create_app(Settings(data_dir=Path("data")))) as restarted:
        assets = restarted.get(f"/api/projects/{project_id}/assets").json()["data"]
        assert len(assets) == 4
        for asset in assets:
            response = restarted.get(asset["file_url"])
            assert response.status_code == 200
            assert response.content.startswith(b"\x89PNG")
        job = restarted.post(
            f"/api/projects/{project_id}/jobs",
            json={"provider": "mock", "clothing_order": clothing_ids},
        )
        assert job.status_code == 201
        job_id = job.json()["data"]["id"]
        assert restarted.get(f"/api/jobs/{job_id}").json()["data"]["status"] == "succeeded"
        outputs = restarted.get(f"/api/jobs/{job_id}/outputs").json()["data"]
        assert len(outputs) == 1
        assert restarted.get(outputs[0]["video_url"]).status_code == 200
    restarted.app.state.engine.dispose()
