from pathlib import Path

from backend.app.config import Settings
from backend.app.db import init_database
from backend.app.models import GenerationJob, Project
from backend.app.services.token_usage import aggregate_job_usage, aggregate_project_usage, record_token_usage


def test_usage_is_upserted_and_aggregated_once_per_step(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    _, factory = init_database(settings)
    with factory() as session:
        project = Project(name="usage")
        session.add(project)
        session.flush()
        job = GenerationJob(project_id=project.id, provider="agnes", status="succeeded")
        session.add(job)
        session.commit()
        project_id, job_id = project.id, job.id

    usage = {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "raw_usage_json": '{"total_tokens":14}'}
    record_token_usage(factory, job_id, "outfit_image_1", "agnes", "image", usage)
    record_token_usage(factory, job_id, "outfit_image_1", "agnes", "image", {**usage, "total_tokens": 16})
    record_token_usage(factory, job_id, "transition_video_1", "agnes", "video", {"total_tokens": 20})

    with factory() as session:
        assert aggregate_job_usage(session, job_id) == {"status": "available", "has_data": True, "input_tokens": 10, "output_tokens": 4, "total_tokens": 36, "step_count": 2}
        assert aggregate_project_usage(session, project_id)["total_tokens"] == 36


def test_missing_provider_usage_is_explicitly_unavailable(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    _, factory = init_database(settings)
    with factory() as session:
        assert aggregate_job_usage(session, "missing") == {"status": "unavailable", "has_data": False, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "step_count": 0}
