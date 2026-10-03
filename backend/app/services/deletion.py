from threading import Lock

from sqlalchemy import select

from ..models import DeletedProject, GenerationJob, Project


TERMINAL_JOB_STATUSES = {"succeeded", "failed", "canceled"}
_running_jobs: set[str] = set()
_running_lock = Lock()


def is_job_executing(job_id: str) -> bool:
    with _running_lock:
        return job_id in _running_jobs


def run_tracked_job(settings, session_factory, job_id: str) -> None:
    """Wrap the existing runner so canceled in-flight calls cannot be deleted."""
    from ..workflow.runner import run_job

    with _running_lock:
        if job_id in _running_jobs:
            return
        _running_jobs.add(job_id)
    try:
        run_job(settings, session_factory, job_id)
    finally:
        with _running_lock:
            _running_jobs.discard(job_id)


def clear_job_checkpoints(settings, job_id: str) -> None:
    from langgraph.checkpoint.sqlite import SqliteSaver

    path = settings.data_dir / "workflow_checkpoints.db"
    if path.is_file():
        with SqliteSaver.from_conn_string(str(path)) as saver:
            saver.setup()
            saver.delete_thread(job_id)


def visible_projects():
    return Project.id.not_in(select(DeletedProject.project_id))


def is_project_deleted(session, project_id: str) -> bool:
    return session.get(DeletedProject, project_id) is not None


def has_active_jobs(session, project_id: str) -> bool:
    active_status = session.scalar(select(GenerationJob.id).where(
        GenerationJob.project_id == project_id,
        GenerationJob.status.not_in(TERMINAL_JOB_STATUSES),
    ).limit(1)) is not None
    return active_status or any(is_job_executing(job_id) for job_id in session.scalars(select(GenerationJob.id).where(GenerationJob.project_id == project_id)))


def mark_project_deleted(session, project: Project) -> None:
    session.add(DeletedProject(project_id=project.id))
    session.commit()
