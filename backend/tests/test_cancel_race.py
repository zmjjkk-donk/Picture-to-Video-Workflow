"""Deterministic cancellation races, without network timing assumptions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import GenerationJob, VideoOutput
from backend.app.providers.base import ProviderStatus
from backend.app.providers.mock import MockVideoProvider
from backend.app.workflow import runner
from backend.tests.test_workflow import prepare_project


@pytest.mark.parametrize("late_status,late_progress", [("processing", 88), ("succeeded", 100)])
def test_cancel_during_provider_reply_keeps_cancel_and_stops_output(tmp_path: Path, monkeypatch, late_status, late_progress):
    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    project, _ = prepare_project(client)
    factory = client.app.state.session_factory
    with factory() as session:
        job = GenerationJob(project_id=project, provider="mock", status="queued")
        session.add(job)
        session.commit()
        job_id = job.id
    progress_at_cancel = []

    class CancelDuringReply(MockVideoProvider):
        def get_video_job_status(self, provider_job_id):
            with factory() as session:
                job = session.get(GenerationJob, job_id)
                progress_at_cancel.append(job.progress)
                job.status = "canceled"
                job.current_node = "canceled"
                job.finished_at = runner.utc_now()
                session.commit()
            return ProviderStatus(late_status, late_progress, "Synthetic late provider reply")

    monkeypatch.setattr(runner, "MockVideoProvider", CancelDuringReply)
    runner.run_job(settings, factory, job_id)
    with factory() as session:
        job = session.get(GenerationJob, job_id)
        assert job.status == "canceled"
        assert job.current_node == "canceled"
        assert job.progress == progress_at_cancel[0]
        assert job.error_code is None
        assert session.query(VideoOutput).filter_by(job_id=job_id).count() == 0


@pytest.mark.parametrize("operation", ["progress", "failure"])
def test_cancel_committed_between_read_and_sql_update_is_atomic(tmp_path: Path, operation):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    project = client.post("/api/projects", json={"name": "原子取消测试"}).json()["data"]["id"]
    factory = client.app.state.session_factory
    with factory() as session:
        job = GenerationJob(project_id=project, provider="mock", status="processing", progress=45)
        session.add(job)
        session.commit()
        job_id = job.id
    fired = []

    def commit_cancel_before_update(_connection, _cursor, statement, _parameters, _context, _many):
        if not fired and statement.lstrip().upper().startswith("UPDATE GENERATION_JOBS"):
            fired.append(True)
            with factory() as other:
                job = other.get(GenerationJob, job_id)
                job.status = "canceled"
                job.current_node = "canceled"
                other.commit()

    engine = client.app.state.engine
    event.listen(engine, "before_cursor_execute", commit_cancel_before_update)
    try:
        if operation == "progress":
            with pytest.raises(runner.WorkflowError, match="任务已取消") as error:
                runner.update_job(factory, job_id, status="succeeded", progress=100, current_node="finish_job")
            assert error.value.code == "JOB_CANCELED"
        else:
            runner._finish_failed(factory, job_id, "SYNTHETIC_LATE_ERROR", "Late model failure")
    finally:
        event.remove(engine, "before_cursor_execute", commit_cancel_before_update)
    assert fired
    with factory() as session:
        job = session.get(GenerationJob, job_id)
        assert (job.status, job.progress, job.current_node) == ("canceled", 45, "canceled")
        assert job.error_code is None
