from pathlib import Path

from sqlalchemy import select

from backend.app.config import Settings
from backend.app.db import init_database
from backend.app.models import Asset, GenerationJob, Project, VideoOutput, WorkflowRun


def test_database_initialization_creates_runtime_files(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    engine, session_factory = init_database(settings)

    assert settings.database_path.exists()
    assert settings.projects_dir.is_dir()
    assert settings.backups_dir.is_dir()

    with session_factory() as session:
        project = Project(name="春季换装演示", description="本地测试项目")
        session.add(project)
        session.flush()
        model = Asset(
            project_id=project.id,
            asset_type="model",
            original_name="model.png",
            stored_path="projects/project/assets/model.png",
            mime_type="image/png",
            file_size=12,
            sha256="a" * 64,
        )
        clothing = Asset(
            project_id=project.id,
            asset_type="clothing",
            display_name="白色针织衫",
            original_name="cloth-1.png",
            stored_path="projects/project/assets/cloth-1.png",
            mime_type="image/png",
            file_size=13,
            sha256="b" * 64,
            slot_index=0,
        )
        session.add_all([model, clothing])
        job = GenerationJob(project_id=project.id, provider="mock")
        session.add(job)
        session.flush()
        session.add(WorkflowRun(job_id=job.id, node_name="validate_assets", sequence=1, status="succeeded"))
        session.add(VideoOutput(job_id=job.id, project_id=project.id, video_path="projects/project/outputs/demo.mp4"))
        session.commit()

    with session_factory() as session:
        saved_project = session.scalar(select(Project).where(Project.name == "春季换装演示"))
        assert saved_project is not None
        assert len(saved_project.assets) == 2
        assert len(saved_project.jobs) == 1
        assert len(saved_project.outputs) == 1
        assert saved_project.jobs[0].workflow_runs[0].node_name == "validate_assets"

    engine.dispose()


def test_project_delete_cascades_to_related_records(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    _, session_factory = init_database(settings)

    with session_factory() as session:
        project = Project(name="待删除项目")
        session.add(project)
        session.flush()
        session.add(Asset(project_id=project.id, asset_type="model", original_name="m.png", stored_path="m.png", mime_type="image/png", file_size=1, sha256="c" * 64))
        job = GenerationJob(project_id=project.id, provider="mock")
        session.add(job)
        session.flush()
        session.add(WorkflowRun(job_id=job.id, node_name="validate_assets", sequence=1, status="succeeded"))
        session.add(VideoOutput(job_id=job.id, project_id=project.id, video_path="demo.mp4"))
        session.commit()
        project_id = project.id
        job_id = job.id
        session.delete(project)
        session.commit()

    with session_factory() as session:
        assert session.get(Project, project_id) is None
        assert session.scalar(select(Asset).where(Asset.project_id == project_id)) is None
        assert session.get(GenerationJob, job_id) is None
        assert session.scalar(select(WorkflowRun).where(WorkflowRun.job_id == job_id)) is None
        assert session.scalar(select(VideoOutput).where(VideoOutput.project_id == project_id)) is None
