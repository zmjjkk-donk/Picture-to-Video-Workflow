from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import TokenUsage
from backend.tests.test_workflow import prepare_project


def test_dashboard_providers_settings_and_failed_job_retry(tmp_path: Path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    project_id, clothing_ids = prepare_project(client)

    summary = client.get("/api/dashboard/summary")
    assert summary.status_code == 200
    assert summary.json()["data"]["project_count"] == 1
    assert summary.json()["data"]["asset_count"] == 4

    providers = client.get("/api/providers").json()["data"]
    assert {provider["name"] for provider in providers} == {"mock", "agnes"}

    settings = client.patch("/api/settings", json={"mode": "mock", "api_key": "must-not-persist"})
    assert settings.status_code == 200
    saved = client.get("/api/settings").json()["data"]
    assert saved["mode"] == "mock"
    assert "api_key" not in saved

    failed = client.post(f"/api/projects/{project_id}/jobs", json={"provider": "agnes", "clothing_order": clothing_ids})
    assert failed.status_code == 201
    failed_job_id = failed.json()["data"]["id"]
    job = client.get(f"/api/jobs/{failed_job_id}").json()["data"]
    assert job["status"] == "failed"
    assert job["error_code"] == "KEY_NOT_CONFIGURED"

    retry = client.post(f"/api/jobs/{failed_job_id}/retry")
    assert retry.status_code == 201
    retry_job_id = retry.json()["data"]["id"]
    retry_job = client.get(f"/api/jobs/{retry_job_id}").json()["data"]
    assert retry_job["status"] == "failed"

    assert client.delete(f"/api/jobs/{retry_job_id}").status_code == 200
    assert client.get(f"/api/jobs/{retry_job_id}").status_code == 404


def test_project_and_job_responses_include_provider_token_usage(tmp_path: Path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    project_id, clothing_ids = prepare_project(client)
    job_response = client.post(f"/api/projects/{project_id}/jobs", json={"provider": "mock", "clothing_order": clothing_ids})
    job_id = job_response.json()["data"]["id"]
    with client.app.state.session_factory() as session:
        session.add(TokenUsage(job_id=job_id, step_key="outfit_image_1", provider="agnes", model="image", input_tokens=2, output_tokens=3, total_tokens=5))
        session.commit()
    project = client.get(f"/api/projects/{project_id}").json()["data"]
    assert project["token_usage_status"] == "available"
    assert project["token_total"] == 5
    job = client.get(f"/api/jobs/{job_id}").json()["data"]
    assert job["token_total"] == 5
    assert client.get(f"/api/projects/{project_id}/token-usage").json()["data"]["total_tokens"] == 5
