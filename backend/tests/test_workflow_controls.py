from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import GenerationJob
from backend.app.workflow.runner import run_job


def test_cancelled_job_is_not_overwritten_by_late_runner(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    project = client.post("/api/projects", json={"name": "取消保护"}).json()["data"]
    with client.app.state.session_factory() as session:
        job = GenerationJob(project_id=project["id"], provider="mock", status="canceled", current_node="canceled")
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    run_job(settings, client.app.state.session_factory, job_id)
    result = client.get(f"/api/jobs/{job_id}").json()["data"]
    assert result["status"] == "canceled"
    assert result["error_code"] is None


def test_resume_route_requeues_same_job(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    project = client.post("/api/projects", json={"name": "恢复任务"}).json()["data"]
    with client.app.state.session_factory() as session:
        job = GenerationJob(project_id=project["id"], provider="mock", status="canceled", current_node="canceled")
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    response = client.post(f"/api/jobs/{job_id}/resume")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == job_id
    assert response.json()["data"]["status"] == "queued"
    assert client.get(f"/api/jobs/{job_id}").json()["data"]["status"] == "failed"
