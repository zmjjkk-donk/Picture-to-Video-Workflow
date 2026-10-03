from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import DeletedProject, GeneratedArtifact, GenerationJob, GenerationStep, Project, TokenUsage, VideoOutput, WorkflowRun
from backend.tests.test_workflow import prepare_project


def test_project_deletion_hides_workspace_but_keeps_history_and_files(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    project_id, clothing_ids = prepare_project(client)
    other_id = client.post("/api/projects", json={"name": "keep me"}).json()["data"]["id"]
    job_id = client.post(f"/api/projects/{project_id}/jobs", json={"provider": "mock", "clothing_order": clothing_ids}).json()["data"]["id"]
    logs = client.get(f"/api/jobs/{job_id}/logs").json()["data"]
    outputs = client.get(f"/api/jobs/{job_id}/outputs").json()["data"]
    assert logs and outputs
    before = {str(p): p.read_bytes() for p in (settings.projects_dir / project_id).rglob("*") if p.is_file()}
    assert client.delete(f"/api/projects/{project_id}").status_code == 200
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert client.get(f"/api/projects/{project_id}/assets").status_code == 404
    for endpoint in ("/api/projects", "/api/dashboard/recent-projects"):
        ids = {p["id"] for p in client.get(endpoint).json()["data"]}
        assert project_id not in ids and other_id in ids
    for endpoint in ("/api/jobs", "/api/dashboard/recent-jobs"):
        job = next(j for j in client.get(endpoint).json()["data"] if j["id"] == job_id)
        assert job["project_deleted"] is True
        assert job["project_name"]
    assert client.get(f"/api/jobs/{job_id}/logs").json()["data"] == logs
    assert client.get(outputs[0]["video_url"]).status_code == 200
    assert client.get(outputs[0]["thumbnail_url"]).status_code == 200
    assert all(Path(path).read_bytes() == content for path, content in before.items())
    summary = client.get("/api/dashboard/summary").json()["data"]
    assert summary == {"project_count": 1, "asset_count": 0, "job_count": 1, "succeeded_count": 1}
    assert client.post(f"/api/projects/{project_id}/jobs", json={"provider": "mock", "clothing_order": clothing_ids}).status_code == 404
    assert client.patch(f"/api/projects/{project_id}", json={"name": "resurrect"}).status_code == 404
    restarted = TestClient(create_app(settings))
    assert restarted.get(f"/api/projects/{project_id}").status_code == 404
    assert restarted.get(f"/api/jobs/{job_id}").json()["data"]["project_deleted"] is True


@pytest.mark.parametrize("status", ["queued", "validating", "preparing", "submitted", "processing"])
def test_project_with_active_job_cannot_be_deleted(tmp_path: Path, status: str):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    project_id = client.post("/api/projects", json={"name": "active"}).json()["data"]["id"]
    with client.app.state.session_factory() as session:
        session.add(GenerationJob(project_id=project_id, status=status))
        session.commit()
    response = client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "PROJECT_HAS_ACTIVE_JOBS"
    assert client.get(f"/api/projects/{project_id}").status_code == 200


def test_deleted_project_backup_restore_preserves_marker_and_history(tmp_path: Path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    project_id, clothing_ids = prepare_project(client)
    job_id = client.post(f"/api/projects/{project_id}/jobs", json={"provider": "mock", "clothing_order": clothing_ids}).json()["data"]["id"]
    assert client.delete(f"/api/projects/{project_id}").status_code == 200
    backup = client.post("/api/backups/export").json()["data"]
    with client.app.state.session_factory() as session:
        session.delete(session.get(DeletedProject, project_id))
        session.commit()
    assert client.get(f"/api/projects/{project_id}").status_code == 200
    assert client.post(f"/api/backups/{backup['id']}/restore?mode=replace").status_code == 200
    assert client.get(f"/api/projects/{project_id}").status_code == 404
    assert client.get("/api/projects").json()["data"] == []
    assert client.get(f"/api/jobs/{job_id}").json()["data"]["project_deleted"] is True
    output = client.get(f"/api/jobs/{job_id}/outputs").json()["data"][0]
    assert client.get(output["video_url"]).status_code == 200


@pytest.mark.parametrize("status", ["failed", "canceled", "succeeded"])
def test_single_task_deletion_cleans_all_records_and_files_only_for_that_task(tmp_path: Path, status: str):
    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    project_id = client.post("/api/projects", json={"name": "keep project"}).json()["data"]["id"]
    with client.app.state.session_factory() as session:
        job = GenerationJob(id="68968372-test", project_id=project_id, status=status)
        sibling = GenerationJob(id="keep-task", project_id=project_id, status="succeeded")
        session.add_all([job, sibling])
        session.flush()
        step = GenerationStep(job_id=job.id, step_key="outfit_image_1")
        session.add(step)
        session.flush()
        session.add_all([
            WorkflowRun(job_id=job.id, node_name="test", sequence=1, status="succeeded"),
            TokenUsage(job_id=job.id, step_key="outfit_image_1", total_tokens=100),
            TokenUsage(job_id=sibling.id, step_key="outfit_image_1", total_tokens=20),
            GeneratedArtifact(job_id=job.id, step_id=step.id, kind="outfit_image", relative_path="unused.png", mime_type="image/png", sha256="a" * 64),
            GeneratedArtifact(job_id=job.id, step_id=None, kind="final_video", relative_path="unused.mp4", mime_type="video/mp4", sha256="b" * 64),
            VideoOutput(job_id=job.id, project_id=project_id, video_path="unused.mp4"),
        ])
        session.commit()
        job_id = job.id
    directories = [settings.projects_dir / project_id / "jobs" / job_id, settings.projects_dir / project_id / "outputs" / job_id]
    for directory in directories:
        directory.mkdir(parents=True)
        (directory / "test.bin").write_bytes(b"delete me")
    sibling_path = settings.projects_dir / project_id / "jobs" / "keep-task" / "keep.png"
    sibling_path.parent.mkdir(parents=True)
    sibling_path.write_bytes(b"keep me")
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.delete(f"/api/jobs/{job_id}").status_code == 404
    for endpoint in ("/api/jobs", "/api/dashboard/recent-jobs"):
        assert {j["id"] for j in client.get(endpoint).json()["data"]} == {"keep-task"}
    assert all(not directory.exists() for directory in directories)
    assert sibling_path.read_bytes() == b"keep me"
    assert client.get(f"/api/projects/{project_id}").json()["data"]["token_total"] == 20
    assert client.get("/api/dashboard/summary").json()["data"]["job_count"] == 1
    with client.app.state.session_factory() as session:
        for model in (WorkflowRun, TokenUsage, GenerationStep, GeneratedArtifact, VideoOutput):
            assert session.scalar(select(model).where(model.job_id == job_id)) is None
        assert session.get(Project, project_id) is not None


@pytest.mark.parametrize("status", ["queued", "validating", "preparing", "submitted", "processing"])
def test_task_cannot_be_deleted_until_stopped(tmp_path: Path, status: str):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    project_id = client.post("/api/projects", json={"name": "active"}).json()["data"]["id"]
    with client.app.state.session_factory() as session:
        job = GenerationJob(project_id=project_id, status=status)
        session.add(job)
        session.commit()
        job_id = job.id
    response = client.delete(f"/api/jobs/{job_id}")
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "JOB_DELETE_NOT_ALLOWED"
    assert client.get(f"/api/jobs/{job_id}").json()["data"]["status"] == status
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200


def test_deleted_project_history_remains_readable_but_cannot_resume_or_retry(tmp_path: Path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    project_id, _ = prepare_project(client)
    with client.app.state.session_factory() as session:
        job = GenerationJob(project_id=project_id, provider="agnes", status="failed")
        session.add(job)
        session.commit()
        job_id = job.id
    assert client.delete(f"/api/projects/{project_id}").status_code == 200
    for action in ("resume", "retry"):
        assert client.post(f"/api/jobs/{job_id}/{action}").status_code == 404
    assert client.get(f"/api/jobs/{job_id}").status_code == 200
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert client.get("/api/jobs").json()["data"] == []


def test_canceled_inflight_worker_must_finish_before_deletion(tmp_path: Path, monkeypatch):
    from threading import Event, Thread
    from backend.app.services.deletion import is_job_executing, run_tracked_job

    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    project_id = client.post("/api/projects", json={"name": "inflight"}).json()["data"]["id"]
    with client.app.state.session_factory() as session:
        job = GenerationJob(project_id=project_id, status="processing")
        session.add(job)
        session.commit()
        job_id = job.id
    started, release = Event(), Event()

    def inflight_runner(*args):
        started.set()
        assert release.wait(10)

    monkeypatch.setattr("backend.app.workflow.runner.run_job", inflight_runner)
    thread = Thread(target=run_tracked_job, args=(settings, client.app.state.session_factory, job_id))
    thread.start()
    try:
        assert started.wait(5)
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
        assert client.delete(f"/api/jobs/{job_id}").json()["detail"]["error"]["code"] == "JOB_STILL_STOPPING"
        assert client.post(f"/api/jobs/{job_id}/resume").status_code == 409
        assert client.delete(f"/api/projects/{project_id}").status_code == 409
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not is_job_executing(job_id)
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert client.delete(f"/api/projects/{project_id}").status_code == 200


def test_task_deletion_removes_only_its_langgraph_checkpoints(tmp_path: Path):
    import sqlite3

    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    project_id, clothing_ids = prepare_project(client)
    job_ids = [client.post(f"/api/projects/{project_id}/jobs", json={"provider": "mock", "clothing_order": clothing_ids}).json()["data"]["id"] for _ in range(2)]
    path = settings.data_dir / "workflow_checkpoints.db"
    with sqlite3.connect(path) as connection:
        for job_id in job_ids:
            assert connection.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id=?", (job_id,)).fetchone()[0] > 0
    assert client.delete(f"/api/jobs/{job_ids[0]}").status_code == 200
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id=?", (job_ids[0],)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM writes WHERE thread_id=?", (job_ids[0],)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id=?", (job_ids[1],)).fetchone()[0] > 0


def test_existing_v3_database_gains_deletion_table_without_losing_records(tmp_path: Path):
    from sqlalchemy import inspect, text

    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    project_id = client.post("/api/projects", json={"name": "third version"}).json()["data"]["id"]
    with client.app.state.session_factory() as session:
        job = GenerationJob(project_id=project_id, status="failed")
        session.add(job)
        session.commit()
        job_id = job.id
    # Simulate a V3 database: all existing tables and data, no deletion table.
    with client.app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE deleted_projects"))
    client.app.state.engine.dispose()
    upgraded = TestClient(create_app(settings))
    assert "deleted_projects" in inspect(upgraded.app.state.engine).get_table_names()
    assert upgraded.get(f"/api/projects/{project_id}").json()["data"]["name"] == "third version"
    assert upgraded.get(f"/api/jobs/{job_id}").json()["data"]["status"] == "failed"
    assert upgraded.delete(f"/api/projects/{project_id}").status_code == 200
    assert upgraded.get(f"/api/jobs/{job_id}").json()["data"]["project_deleted"] is True
