from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select, update

from ..config import Settings
from ..models import Asset, GeneratedArtifact, GenerationJob, GenerationStep, Project, VideoOutput, WorkflowRun
from ..providers.base import VideoJobRequest, VideoProvider
from ..providers.mock import MockVideoProvider
from ..providers.agnes_common import AgnesError
from ..providers.agnes_image import AgnesImageProvider
from ..providers.agnes_video import AgnesVideoProvider
from ..services.media import MediaComposeError, compose_segments
from ..services.token_usage import record_token_usage


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
    outfit_paths: list[str]
    outfit_urls: list[str | None]
    segment_paths: list[str]
    video_ids: list[str]


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
    if name == "agnes":
        raise WorkflowError("PROVIDER_WORKFLOW_REQUIRED", "Agnes 使用多阶段图像和视频工作流")
    raise WorkflowError("PROVIDER_NOT_SUPPORTED", f"不支持的 Provider: {name}")


def record_node(session_factory, job_id: str, node_name: str, sequence: int, status: str, input_summary: str = "", output_summary: str = "", error_message: str | None = None) -> None:
    with session_factory() as session:
        session.add(WorkflowRun(job_id=job_id, node_name=node_name, sequence=sequence, status=status, input_summary=input_summary, output_summary=output_summary, error_message=error_message, finished_at=utc_now() if status in {"succeeded", "failed"} else None))
        session.commit()


def update_job(session_factory, job_id: str, **changes) -> None:
    if not changes:
        return
    with session_factory() as session:
        # A cancellation may commit after ensure_job_active or a stale read.
        # Check the status in the same SQL write so late replies cannot undo it.
        result = session.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id, GenerationJob.status != "canceled")
            .values(**changes)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            job = session.get(GenerationJob, job_id)
            if job is not None and job.status == "canceled":
                raise WorkflowError("JOB_CANCELED", "任务已取消")
            return
        session.commit()


def ensure_job_active(session_factory, job_id: str) -> None:
    """Stop a local workflow as soon as the user has cancelled it."""
    with session_factory() as session:
        job = session.get(GenerationJob, job_id)
        if job is None:
            raise WorkflowError("JOB_NOT_FOUND", "生成任务不存在")
        if job.status == "canceled":
            raise WorkflowError("JOB_CANCELED", "任务已取消")


def build_graph(settings: Settings, session_factory, provider: VideoProvider, checkpointer=None):
    def validate_assets(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        ensure_job_active(session_factory, job_id)
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
        ensure_job_active(session_factory, job_id)
        prompt = "竖屏 9:16 电商换装视频，模特依次展示三套服装，保持脸部、发型、身材比例、背景和光线一致，准确还原服装颜色、版型、纹理、图案和关键设计，换装自然，避免闪烁、穿模、服装漂移和身份变化。"
        update_job(session_factory, job_id, status="preparing", progress=30, current_node="prepare_prompt")
        record_node(session_factory, job_id, "prepare_prompt", 2, "succeeded", output_summary="已生成换装约束提示词")
        return {"prompt": prompt, "progress": 30, "current_node": "prepare_prompt"}

    def submit_video_job(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        ensure_job_active(session_factory, job_id)
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
        attempts = 6
        interval = 0.05
        for _ in range(attempts):
            ensure_job_active(session_factory, job_id)
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
        ensure_job_active(session_factory, job_id)
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


def _record_generation_step(session_factory, job_id: str, step_key: str, model: str, status: str = "running", provider_job_id: str | None = None, progress: int = 0, error_message: str | None = None) -> GenerationStep:
    with session_factory() as session:
        step = session.query(GenerationStep).filter_by(job_id=job_id, step_key=step_key, attempt=1).first()
        if step is None:
            step = GenerationStep(job_id=job_id, step_key=step_key, attempt=1, provider="agnes", model=model, status=status, provider_job_id=provider_job_id, progress=progress, started_at=utc_now())
            session.add(step)
        else:
            step.status = status
            step.provider_job_id = provider_job_id or step.provider_job_id
            step.progress = progress
            step.error_message = error_message
        if status in {"succeeded", "failed", "canceled"}:
            step.finished_at = utc_now()
        session.commit()
        session.refresh(step)
        return step


def _save_artifact(session_factory, settings: Settings, job_id: str, step_id: str | None, kind: str, path, slot_index: int | None = None, remote_url: str | None = None) -> None:
    import hashlib
    from PIL import Image

    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = settings.data_dir / file_path
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    width = height = None
    duration = None
    if kind in {"outfit_image", "cover"}:
        with Image.open(file_path) as image:
            width, height = image.size
    mime_type = "image/png" if kind in {"outfit_image", "cover"} else "video/mp4"
    with session_factory() as session:
        session.add(GeneratedArtifact(job_id=job_id, step_id=step_id, kind=kind, slot_index=slot_index, relative_path=str(file_path.relative_to(settings.data_dir)).replace("\\", "/"), mime_type=mime_type, sha256=digest, file_size=file_path.stat().st_size, width=width, height=height, duration=duration, remote_url=remote_url))
        session.commit()


def build_agnes_graph(settings: Settings, session_factory, checkpointer=None):
    image_provider = AgnesImageProvider(settings)
    video_provider = AgnesVideoProvider(settings)

    def validate_assets(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        ensure_job_active(session_factory, job_id)
        update_job(session_factory, job_id, status="validating", progress=5, current_node="validate_assets", started_at=utc_now())
        with session_factory() as session:
            project = session.get(Project, state["project_id"])
            if project is None:
                raise WorkflowError("PROJECT_NOT_FOUND", "项目不存在")
            model = [asset for asset in project.assets if asset.asset_type == "model"]
            clothing = sorted([asset for asset in project.assets if asset.asset_type == "clothing"], key=lambda asset: asset.slot_index or 0)
            if len(model) != 1 or len(clothing) != 3:
                raise WorkflowError("ASSET_COUNT_INVALID", "Agnes 工作流必须包含一张模特图和三张服装图")
            return {"asset_ids": [model[0].id, *[asset.id for asset in clothing]], "progress": 10, "current_node": "validate_assets"}

    def prepare_prompt(state: WorkflowState) -> WorkflowState:
        ensure_job_active(session_factory, state["job_id"])
        update_job(session_factory, state["job_id"], status="preparing", progress=12, current_node="prepare_prompts")
        return {"prompt": "电商服装换装素材，保持同一模特的脸部、发型、身材比例、姿态、背景和光线一致，只将第二张参考图中的服装自然穿到第一张模特图上，准确还原服装颜色、版型、纹理、图案和关键设计，不添加饰品，不改变人物身份，竖幅全身构图。", "progress": 12, "current_node": "prepare_prompts"}

    def generate_outfits(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        with session_factory() as session:
            project = session.get(Project, state["project_id"])
            model = next(asset for asset in project.assets if asset.asset_type == "model")
            clothing = sorted([asset for asset in project.assets if asset.asset_type == "clothing"], key=lambda asset: asset.slot_index or 0)
            output_dir = settings.projects_dir / project.id / "jobs" / job_id / "outfits"
            model_path = settings.data_dir / model.stored_path
            clothing_paths = [settings.data_dir / asset.stored_path for asset in clothing]
        outfit_paths: list[str] = []
        outfit_urls: list[str | None] = []
        for index, clothing_path in enumerate(clothing_paths):
            ensure_job_active(session_factory, job_id)
            step = _record_generation_step(session_factory, job_id, f"outfit_image_{index + 1}", settings.agnes_image_model)
            output_path = output_dir / f"look-{index + 1:02d}.png"
            remote_url = None
            with session_factory() as session:
                existing = session.scalar(select(GeneratedArtifact).where(GeneratedArtifact.job_id == job_id, GeneratedArtifact.kind == "outfit_image", GeneratedArtifact.slot_index == index).order_by(GeneratedArtifact.created_at.desc()))
            if existing and (settings.data_dir / existing.relative_path).is_file():
                output_path = settings.data_dir / existing.relative_path
                remote_url = existing.remote_url
            else:
                remote_url = image_provider.generate_outfit_image(model_path, clothing_path, state["prompt"], output_path)
                record_token_usage(session_factory, job_id, f"outfit_image_{index + 1}", "agnes", settings.agnes_image_model, getattr(image_provider, "last_usage", None))
                _save_artifact(session_factory, settings, job_id, step.id, "outfit_image", output_path, index, remote_url)
            _record_generation_step(session_factory, job_id, f"outfit_image_{index + 1}", settings.agnes_image_model, "succeeded", progress=100)
            outfit_paths.append(str(output_path))
            outfit_urls.append(remote_url)
            update_job(session_factory, job_id, progress=15 + (index + 1) * 10, current_node=f"generate_outfit_{index + 1}")
        return {"outfit_paths": outfit_paths, "outfit_urls": outfit_urls, "progress": 45, "current_node": "outfits_ready"}

    def generate_segments(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        segment_paths: list[str] = []
        video_ids: list[str] = []
        for index in range(2):
            ensure_job_active(session_factory, job_id)
            step_key = f"transition_video_{index + 1}"
            prompt = "保持同一模特、脸部、发型、身材比例、背景和光线不变，镜头稳定，从首帧服装自然、连续地过渡到尾帧服装，避免闪烁、穿模、身体异常、服装漂移和额外人物。"
            with session_factory() as session:
                existing_step = session.scalar(select(GenerationStep).where(GenerationStep.job_id == job_id, GenerationStep.step_key == step_key, GenerationStep.attempt == 1))
                existing_artifact = session.scalar(select(GeneratedArtifact).where(GeneratedArtifact.job_id == job_id, GeneratedArtifact.kind == "transition_video", GeneratedArtifact.slot_index == index).order_by(GeneratedArtifact.created_at.desc()))
            existing_segment = settings.data_dir / existing_artifact.relative_path if existing_artifact else None
            if existing_segment and existing_segment.is_file() and existing_step and existing_step.status == "succeeded":
                segment_paths.append(str(existing_segment))
                video_ids.append(existing_step.provider_job_id or f"recovered-{index + 1}")
                continue
            step = _record_generation_step(session_factory, job_id, step_key, settings.agnes_video_model)
            video_id = (existing_step.provider_job_id if existing_step and existing_step.status == "processing" and existing_step.provider_job_id else None) or video_provider.submit_keyframe_job(state["outfit_urls"][index], state["outfit_urls"][index + 1], prompt)
            record_token_usage(session_factory, job_id, step_key, "agnes", settings.agnes_video_model, getattr(video_provider, "last_usage", None))
            _record_generation_step(session_factory, job_id, step_key, settings.agnes_video_model, "processing", video_id, 1)
            deadline = time.monotonic() + settings.agnes_video_timeout_seconds
            while time.monotonic() < deadline:
                ensure_job_active(session_factory, job_id)
                status, progress, _message = video_provider.get_status(video_id)
                record_token_usage(session_factory, job_id, step_key, "agnes", settings.agnes_video_model, getattr(video_provider, "last_usage", None))
                _record_generation_step(session_factory, job_id, step_key, settings.agnes_video_model, "processing", video_id, progress)
                update_job(session_factory, job_id, status="processing", progress=45 + index * 15 + min(progress // 4, 20), current_node=f"poll_transition_{index + 1}")
                if status == "succeeded":
                    break
                time.sleep(settings.agnes_poll_interval_seconds)
            else:
                raise AgnesError("PROVIDER_TIMEOUT", f"Agnes 视频段 {index + 1} 超时")
            with session_factory() as session:
                project = session.get(Project, state["project_id"])
                output_path = settings.projects_dir / project.id / "jobs" / job_id / "segments" / f"transition-{index + 1:02d}.mp4"
            video_provider.download_video(video_id, output_path)
            _save_artifact(session_factory, settings, job_id, step.id, "transition_video", output_path, index)
            _record_generation_step(session_factory, job_id, step_key, settings.agnes_video_model, "succeeded", video_id, 100)
            segment_paths.append(str(output_path))
            video_ids.append(video_id)
        return {"segment_paths": segment_paths, "video_ids": video_ids, "progress": 80, "current_node": "segments_ready"}

    def compose_output(state: WorkflowState) -> WorkflowState:
        job_id = state["job_id"]
        ensure_job_active(session_factory, job_id)
        with session_factory() as session:
            project = session.get(Project, state["project_id"])
            output_dir = settings.projects_dir / project.id / "outputs" / job_id
        output_path = output_dir / "final.mp4"
        cover_source = Path(state["outfit_paths"][0])
        try:
            width, height, duration = compose_segments([Path(item) for item in state["segment_paths"]], output_path, cover_source, target_seconds=float(project.duration_seconds))
        except MediaComposeError as exc:
            raise WorkflowError("COMPOSE_FAILED", str(exc)) from exc
        cover_path = output_path.with_name("cover.png")
        _save_artifact(session_factory, settings, job_id, None, "final_video", output_path)
        _save_artifact(session_factory, settings, job_id, None, "cover", cover_path)
        import hashlib
        with session_factory() as session:
            project = session.get(Project, state["project_id"])
            digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
            session.add(VideoOutput(job_id=job_id, project_id=project.id, video_path=str(output_path.relative_to(settings.data_dir)).replace("\\", "/"), thumbnail_path=str(cover_path.relative_to(settings.data_dir)).replace("\\", "/"), width=width, height=height, duration=duration, file_size=output_path.stat().st_size, sha256=digest))
            project.status = "completed"
            session.commit()
        update_job(session_factory, job_id, status="succeeded", progress=100, current_node="finish_job", finished_at=utc_now())
        return {"progress": 100, "current_node": "finish_job", "status": "succeeded"}

    graph = StateGraph(WorkflowState)
    graph.add_node("validate_assets", validate_assets)
    graph.add_node("prepare_prompts", prepare_prompt)
    graph.add_node("generate_outfits", generate_outfits)
    graph.add_node("generate_segments", generate_segments)
    graph.add_node("compose_output", compose_output)
    graph.add_edge(START, "validate_assets")
    graph.add_edge("validate_assets", "prepare_prompts")
    graph.add_edge("prepare_prompts", "generate_outfits")
    graph.add_edge("generate_outfits", "generate_segments")
    graph.add_edge("generate_segments", "compose_output")
    graph.add_edge("compose_output", END)
    return graph.compile(checkpointer=checkpointer)


def run_job(settings: Settings, session_factory, job_id: str) -> None:
    with session_factory() as session:
        job = session.get(GenerationJob, job_id)
        if job is None:
            return
        project_id = job.project_id
        provider_name = job.provider
    state: WorkflowState = {"job_id": job_id, "project_id": project_id, "provider_name": provider_name, "status": "queued", "progress": 0, "current_node": "queued"}
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = settings.data_dir / "workflow_checkpoints.db"
        with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
            checkpointer.setup()
            if provider_name == "agnes":
                graph = build_agnes_graph(settings, session_factory, checkpointer)
            elif provider_name == "mock":
                graph = build_graph(settings, session_factory, MockVideoProvider(), checkpointer)
            else:
                raise WorkflowError("PROVIDER_NOT_SUPPORTED", f"历史 Provider {provider_name} 不支持新任务")
            graph.invoke(state, config={"configurable": {"thread_id": job_id}})
    except AgnesError as exc:
        _finish_failed(session_factory, job_id, exc.code, exc.message)
    except WorkflowError as exc:
        _finish_failed(session_factory, job_id, exc.code, exc.message)
    except Exception as exc:
        _finish_failed(session_factory, job_id, "WORKFLOW_INTERNAL_ERROR", str(exc))


def _finish_failed(session_factory, job_id: str, code: str, message: str) -> None:
    """Persist failures without overwriting an explicit local cancellation."""
    with session_factory() as session:
        job = session.get(GenerationJob, job_id)
        if job is None or job.status == "canceled":
            return
    try:
        update_job(session_factory, job_id, status="failed", progress=0, current_node="failed", error_code=code, error_message=message, finished_at=utc_now())
    except WorkflowError as exc:
        if exc.code == "JOB_CANCELED":
            return  # Cancellation committed between the read and the failure write.
        raise
    record_node(session_factory, job_id, "workflow", 99, "failed", error_message=message)
