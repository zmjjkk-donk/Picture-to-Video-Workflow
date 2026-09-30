from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from ..config import Settings
from ..models import Asset, GenerationJob, Project, VideoOutput, WorkflowRun
from ..providers.base import VideoJobRequest, VideoProvider
from ..providers.mock import MockVideoProvider
from ..providers.siliconflow import SiliconFlowVideoProvider


class WorkflowState(TypedDict, total=False):
    job_id: str
    project_id: str
    provider_name: str
    asset_ids: list[str]
    prompt: str
    provider_job_id: str
    status: str
    progress: int
    current_node: str
    output_path: str
    error: str


class WorkflowError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def provider_for(name: str, settings: Settings | None = None) -> VideoProvider:
    if name == "mock":
        return MockVideoProvider()
    if name == "siliconflow":
        return SiliconFlowVideoProvider(settings)
    raise WorkflowError("PROVIDER_NOT_SUPPORTED", f"不支持的 Provider: {name}")


def record_node(session_factory, job_id: str, node_name: str, sequence: int, status: str, input_summary: str = "", output_summary: str = "", error_message: str | None = None) -> None:
    with session_factory() as session:
        session.add(WorkflowRun(job_id=job_id, node_name=node_name, sequence=sequence, status=status, input_summary=input_summary, output_summary=output_summary, error_message=error_message, finished_at=utc_now() if status in {"succeeded", "failed"} else None))
        session.commit()


def update_job(session_factory, job_id: str, **changes) -> None:
    with session_factory() as session:
        job = session.get(GenerationJob, job_id)
        if job is None:
            return
        for key, value in changes.items():
            setattr(job, key, value)
        session.commit()


def build_graph(settings: Settings, session_factory, provider: VideoProvider, checkpointer=None):
    def validate_assets(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        record_node(session_factory, job_id, "validate_assets", 1, "running", "检查模特图和三张服装图")
        update_job(session_factory, job_id, status="validating", progress=10, current_node="validate_assets", started_at=utc_now())
        with session_factory() as session:
            project = session.get(Project, state["project_id"])
            if project is None:
                raise WorkflowError("PROJECT_NOT_FOUND", "项目不存在")
            assets = list(session.scalars(select(Asset).where(Asset.project_id == project.id)).all())
            if sum(asset.asset_type == "model" for asset in assets) != 1:
                raise WorkflowError("MODEL_ASSET_REQUIRED", "项目必须包含一张模特图")
            clothing = [asset for asset in assets if asset.asset_type == "clothing"]
            if len(clothing) != 3:
                raise WorkflowError("CLOTHING_ASSET_COUNT_INVALID", "项目必须包含三张服装图")
        record_node(session_factory, job_id, "validate_assets", 1, "succeeded", output_summary="素材校验通过")
        return {"asset_ids": [asset.id for asset in assets], "progress": 20, "current_node": "validate_assets"}

    def prepare_prompt(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        prompt = "竖屏 9:16 电商换装视频，模特依次展示三套服装，保持脸部、发型、身材比例、背景和光线一致，准确还原服装颜色、版型、纹理、图案和关键设计，换装自然，避免闪烁、穿模、服装漂移和身份变化。"
        update_job(session_factory, job_id, status="preparing", progress=30, current_node="prepare_prompt")
        record_node(session_factory, job_id, "prepare_prompt", 2, "succeeded", output_summary="已生成换装约束提示词")
        return {"prompt": prompt, "progress": 30, "current_node": "prepare_prompt"}

    def submit_video_job(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        with session_factory() as session:
            project = session.get(Project, state["project_id"])
            if project is None:
                raise WorkflowError("PROJECT_NOT_FOUND", "项目不存在")
            model_asset = next(asset for asset in project.assets if asset.asset_type == "model")
            clothing_assets = tuple(asset for asset in project.assets if asset.asset_type == "clothing")
            request = VideoJobRequest(job_id=job_id, prompt=state["prompt"], output_dir=settings.projects_dir / project.id / "outputs" / job_id, duration_seconds=project.duration_seconds, video_ratio=project.video_ratio, image_path=settings.data_dir / model_asset.stored_path, reference_image_paths=tuple(settings.data_dir / asset.stored_path for asset in clothing_assets))
        try:
            provider.validate_config()
            provider_job_id = provider.submit_video_job(request)
        except Exception as exc:
            raise WorkflowError("PROVIDER_SUBMIT_FAILED", str(exc)) from exc
        update_job(session_factory, job_id, status="submitted", progress=45, current_node="submit_video_job", provider_job_id=provider_job_id)
        record_node(session_factory, job_id, "submit_video_job", 3, "succeeded", output_summary=f"Provider 任务已提交: {provider_job_id}")
        return {"provider_job_id": provider_job_id, "progress": 45, "current_node": "submit_video_job"}

    def poll_video_job(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        attempts = settings.siliconflow_poll_attempts if provider.name == "siliconflow" else 6
        interval = settings.siliconflow_poll_interval_seconds if provider.name == "siliconflow" else 0.05
        for _ in range(attempts):
            provider_status = provider.get_video_job_status(state["provider_job_id"])
            update_job(session_factory, job_id, status="processing" if provider_status.status == "processing" else provider_status.status, progress=provider_status.progress, current_node="poll_video_job")
            if provider_status.status == "succeeded":
                record_node(session_factory, job_id, "poll_video_job", 4, "succeeded", output_summary=provider_status.message)
                return {"status": "succeeded", "progress": 80, "current_node": "poll_video_job"}
            if provider_status.status == "failed":
                raise WorkflowError("PROVIDER_GENERATION_FAILED", provider_status.message)
            time.sleep(interval)
        raise WorkflowError("PROVIDER_TIMEOUT", "Provider 任务超时")

    def save_output(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        with session_factory() as session:
            job = session.get(GenerationJob, job_id)
            project = session.get(Project, state["project_id"])
            if job is None or project is None:
                raise WorkflowError("PROJECT_NOT_FOUND", "项目或任务不存在")
            output_dir = settings.projects_dir / project.id / "outputs" / job_id
        try:
            result = provider.download_video(state["provider_job_id"], output_dir)
        except Exception as exc:
            raise WorkflowError("OUTPUT_GENERATION_FAILED", str(exc)) from exc
        digest = hashlib.sha256(result.video_path.read_bytes()).hexdigest()
        with session_factory() as session:
            job = session.get(GenerationJob, job_id)
            project = session.get(Project, state["project_id"])
            if job is None or project is None:
                raise WorkflowError("PROJECT_NOT_FOUND", "项目或任务不存在")
            session.add(VideoOutput(job_id=job.id, project_id=project.id, video_path=str(result.video_path.relative_to(settings.data_dir)).replace("\\", "/"), thumbnail_path=str(result.thumbnail_path.relative_to(settings.data_dir)).replace("\\", "/"), width=result.width, height=result.height, duration=result.duration, file_size=result.video_path.stat().st_size, sha256=digest))
            project.status = "completed"
            session.commit()
        update_job(session_factory, job_id, status="succeeded", progress=100, current_node="finish_job", finished_at=utc_now())
        record_node(session_factory, job_id, "save_output", 5, "succeeded", output_summary="视频和封面已保存")
        return {"status": "succeeded", "progress": 100, "current_node": "finish_job", "output_path": str(result.video_path)}

    graph = StateGraph(WorkflowState)
    graph.add_node("validate_assets", validate_assets)
    graph.add_node("prepare_prompt", prepare_prompt)
    graph.add_node("submit_video_job", submit_video_job)
    graph.add_node("poll_video_job", poll_video_job)
    graph.add_node("save_output", save_output)
    graph.add_edge(START, "validate_assets")
    graph.add_edge("validate_assets", "prepare_prompt")
    graph.add_edge("prepare_prompt", "submit_video_job")
    graph.add_edge("submit_video_job", "poll_video_job")
    graph.add_edge("poll_video_job", "save_output")
    graph.add_edge("save_output", END)
    return graph.compile(checkpointer=checkpointer)


def run_job(settings: Settings, session_factory, job_id: str) -> None:
    with session_factory() as session:
        job = session.get(GenerationJob, job_id)
        if job is None:
            return
        project_id = job.project_id
        provider_name = job.provider
    provider = provider_for(provider_name, settings)
    state: WorkflowState = {"job_id": job_id, "project_id": project_id, "provider_name": provider_name, "status": "queued", "progress": 0, "current_node": "queued"}
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = settings.data_dir / "workflow_checkpoints.db"
        with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
            checkpointer.setup()
            graph = build_graph(settings, session_factory, provider, checkpointer)
            graph.invoke(state, config={"configurable": {"thread_id": job_id}})
    except WorkflowError as exc:
        update_job(session_factory, job_id, status="failed", progress=0, current_node="failed", error_code=exc.code, error_message=exc.message, finished_at=utc_now())
        record_node(session_factory, job_id, "workflow", 99, "failed", error_message=exc.message)
    except Exception as exc:
        update_job(session_factory, job_id, status="failed", progress=0, current_node="failed", error_code="WORKFLOW_INTERNAL_ERROR", error_message=str(exc), finished_at=utc_now())
        record_node(session_factory, job_id, "workflow", 99, "failed", error_message=str(exc))
