from __future__ import annotations

import hashlib
import json
import io
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AppSetting, Asset, BackupRecord, GeneratedArtifact, GenerationJob, GenerationStep, Project, VideoOutput, WorkflowRun
from ..schemas import (
    AssetResponse,
    AssetUpdate,
    HealthResponse,
    JobCreate,
    JobResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    ReorderRequest,
)
from .deps import get_session
from ..workflow.runner import run_job
from ..providers.agnes_common import AgnesNotConfigured
from ..providers.agnes_image import AgnesImageProvider
from ..services.backup import BackupError, export_backup, import_backup, restore_backup
from ..db import init_database


router = APIRouter(prefix="/api")
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def request_id() -> str:
    return str(uuid4())


def success(data, message: str = "操作成功") -> dict:
    return {"success": True, "data": data, "message": message, "request_id": request_id()}


def fail(code: str, message: str, http_status: int = 400) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"success": False, "error": {"code": code, "message": message}, "request_id": request_id()},
    )


def project_response(project: Project) -> dict:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status,
        video_ratio=project.video_ratio,
        duration_seconds=project.duration_seconds,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
        asset_count=len(project.assets),
        job_count=len(project.jobs),
    ).model_dump(mode="json")


def asset_response(request: Request, asset: Asset) -> dict:
    base = str(request.base_url).rstrip("/")
    return AssetResponse(
        id=asset.id,
        project_id=asset.project_id,
        asset_type=asset.asset_type,
        original_name=asset.original_name,
        display_name=asset.display_name,
        stored_path=asset.stored_path,
        mime_type=asset.mime_type,
        file_size=asset.file_size,
        sha256=asset.sha256,
        width=asset.width,
        height=asset.height,
        slot_index=asset.slot_index,
        created_at=asset.created_at,
        file_url=f"{base}/api/assets/{asset.id}/file",
        thumbnail_url=f"{base}/api/assets/{asset.id}/thumbnail",
    ).model_dump(mode="json")


def job_response(job: GenerationJob) -> dict:
    return JobResponse.model_validate(job).model_dump(mode="json")


def get_project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise fail("PROJECT_NOT_FOUND", "项目不存在", 404)
    return project


def safe_project_dir(request: Request, project_id: str) -> Path:
    root = request.app.state.settings.projects_dir.resolve()
    candidate = (root / project_id).resolve()
    if root not in candidate.parents and candidate != root:
        raise fail("INVALID_PATH", "项目路径无效", 400)
    return candidate


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    with request.app.state.session_factory() as session:
        session.execute(select(1))
    settings = request.app.state.settings
    return HealthResponse(status="ok", app_name=settings.app_name, version=settings.app_version, database="ok")


@router.get("/system/info")
def system_info(request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings
    selected = session.get(AppSetting, "mode")
    return success({"app_name": settings.app_name, "version": settings.app_version, "data_dir": str(settings.data_dir), "mode": json.loads(selected.value_json) if selected else "mock"})


@router.get("/system/storage")
def system_storage(request: Request):
    settings = request.app.state.settings
    total_size = sum(path.stat().st_size for path in settings.data_dir.rglob("*") if path.is_file()) if settings.data_dir.exists() else 0
    return success({"data_dir": str(settings.data_dir), "bytes_used": total_size})


@router.get("/projects")
def list_projects(session: Session = Depends(get_session)):
    projects = session.scalars(select(Project).order_by(Project.updated_at.desc())).all()
    return success([project_response(project) for project in projects])


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)):
    project = Project(name=payload.name, description=payload.description, video_ratio=payload.video_ratio, duration_seconds=payload.duration_seconds)
    session.add(project)
    session.commit()
    session.refresh(project)
    return success(project_response(project), "项目创建成功")


@router.get("/projects/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_session)):
    return success(project_response(get_project_or_404(session, project_id)))


@router.patch("/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate, session: Session = Depends(get_session)):
    project = get_project_or_404(session, project_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    project.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(project)
    return success(project_response(project), "项目更新成功")


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, request: Request, session: Session = Depends(get_session)):
    project = get_project_or_404(session, project_id)
    project_dir = safe_project_dir(request, project_id)
    session.delete(project)
    session.commit()
    if project_dir.exists():
        shutil.rmtree(project_dir)
    return success(None, "项目删除成功")


@router.post("/projects/{project_id}/archive")
def archive_project(project_id: str, session: Session = Depends(get_session)):
    project = get_project_or_404(session, project_id)
    project.status = "archived"
    project.archived_at = datetime.now(timezone.utc)
    project.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(project)
    return success(project_response(project), "项目已归档")


@router.post("/projects/{project_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_project(project_id: str, request: Request, session: Session = Depends(get_session)):
    project = get_project_or_404(session, project_id)
    copied = Project(name=f"{project.name} - 副本", description=project.description, video_ratio=project.video_ratio, duration_seconds=project.duration_seconds)
    session.add(copied)
    session.flush()
    source_dir = safe_project_dir(request, project_id)
    target_dir = safe_project_dir(request, copied.id)
    if source_dir.exists():
        shutil.copytree(source_dir, target_dir)
    session.commit()
    session.refresh(copied)
    return success(project_response(copied), "项目复制成功")


async def read_image_upload(upload: UploadFile, max_size: int) -> tuple[bytes, str, int, int]:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise fail("FILE_TYPE_NOT_SUPPORTED", "仅支持 PNG、JPG、JPEG 或 WEBP 图片")
    content = await upload.read(max_size + 1)
    if len(content) > max_size:
        raise fail("FILE_TOO_LARGE", "图片超过大小限制")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise fail("INVALID_IMAGE_FILE", "上传文件不是有效图片") from exc
    return content, upload.content_type, width, height


async def save_asset(request: Request, session: Session, project: Project, upload: UploadFile, asset_type: str, display_name: str, slot_index: int | None, replace_existing: Asset | None = None) -> Asset:
    if replace_existing is None and asset_type == "model" and any(asset.asset_type == "model" for asset in project.assets):
        raise fail("MODEL_ASSET_LIMIT", "一个项目只能有一张模特图")
    if replace_existing is None and asset_type == "clothing" and sum(asset.asset_type == "clothing" for asset in project.assets) >= 3:
        raise fail("CLOTHING_ASSET_LIMIT", "一个项目最多上传三张服装图")
    content, mime_type, width, height = await read_image_upload(upload, request.app.state.settings.max_upload_size)
    old_path = None
    asset = replace_existing
    if asset is None:
        asset = Asset(
            project_id=project.id,
            asset_type=asset_type,
            original_name=Path(upload.filename or "upload").name,
            display_name=display_name,
            stored_path="",
            mime_type=mime_type,
            file_size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            width=width,
            height=height,
            slot_index=slot_index,
        )
        session.add(asset)
        session.flush()
    else:
        old_path = (request.app.state.settings.data_dir / asset.stored_path).resolve() if asset.stored_path else None
        asset.original_name = Path(upload.filename or "upload").name
        asset.display_name = display_name
        asset.mime_type = mime_type
        asset.file_size = len(content)
        asset.sha256 = hashlib.sha256(content).hexdigest()
        asset.width = width
        asset.height = height
        asset.slot_index = slot_index
    project_dir = safe_project_dir(request, project.id) / "assets"
    project_dir.mkdir(parents=True, exist_ok=True)
    extension = Path(upload.filename or ".img").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        extension = ".png" if mime_type == "image/png" else ".jpg"
    stored_path = project_dir / f"{asset.id}{extension}"
    stored_path.write_bytes(content)
    asset.stored_path = str(stored_path.relative_to(request.app.state.settings.data_dir)).replace("\\", "/")
    if asset_type == "clothing" and asset.slot_index is None:
        asset.slot_index = sum(item.asset_type == "clothing" for item in project.assets if item.id != asset.id)
    session.commit()
    session.refresh(asset)
    if old_path and old_path != stored_path and old_path.is_file():
        old_path.unlink()
    return asset


@router.get("/projects/{project_id}/assets")
def list_assets(project_id: str, request: Request, session: Session = Depends(get_session)):
    project = get_project_or_404(session, project_id)
    assets = sorted(project.assets, key=lambda asset: (asset.asset_type != "model", asset.slot_index if asset.slot_index is not None else 99))
    return success([asset_response(request, asset) for asset in assets])


@router.post("/projects/{project_id}/assets/model", status_code=status.HTTP_201_CREATED)
async def upload_model(project_id: str, request: Request, file: UploadFile = File(...), session: Session = Depends(get_session)):
    project = get_project_or_404(session, project_id)
    existing = next((item for item in project.assets if item.asset_type == "model"), None)
    asset = await save_asset(request, session, project, file, "model", "模特图", None, existing)
    if sum(item.asset_type == "clothing" for item in project.assets) == 3:
        project.status = "ready"
        session.commit()
    return success(asset_response(request, asset), "模特图上传成功")


@router.post("/projects/{project_id}/assets/clothing", status_code=status.HTTP_201_CREATED)
async def upload_clothing(project_id: str, request: Request, name: str = Form(""), slot_index: int | None = Form(None), file: UploadFile = File(...), session: Session = Depends(get_session)):
    project = get_project_or_404(session, project_id)
    # Older clients sent these values as query parameters; keep that shape
    # compatible while accepting the multipart form fields used by the web UI.
    if not name and request.query_params.get("name"):
        name = request.query_params["name"]
    if slot_index is None and request.query_params.get("slot_index") is not None:
        try:
            slot_index = int(request.query_params["slot_index"])
        except ValueError as exc:
            raise fail("INVALID_SLOT_INDEX", "服装顺序必须是 0、1 或 2") from exc
    if slot_index is not None and slot_index not in {0, 1, 2}:
        raise fail("INVALID_SLOT_INDEX", "服装顺序必须是 0、1 或 2")
    clothing_count = sum(item.asset_type == "clothing" for item in project.assets)
    existing = next((item for item in project.assets if item.asset_type == "clothing" and item.slot_index == slot_index), None) if slot_index is not None else None
    asset = await save_asset(request, session, project, file, "clothing", name.strip() or Path(file.filename or "服装").stem, slot_index, existing)
    if clothing_count + 1 == 3 and any(item.asset_type == "model" for item in project.assets):
        project.status = "ready"
        session.commit()
    return success(asset_response(request, asset), "服装图上传成功")


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: str, payload: AssetUpdate, session: Session = Depends(get_session)):
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise fail("ASSET_NOT_FOUND", "素材不存在", 404)
    if payload.display_name is not None:
        asset.display_name = payload.display_name
    if payload.slot_index is not None:
        conflict = session.scalar(select(Asset).where(Asset.project_id == asset.project_id, Asset.asset_type == "clothing", Asset.slot_index == payload.slot_index, Asset.id != asset.id))
        if conflict:
            raise fail("SLOT_ALREADY_USED", "服装顺序位置已被占用")
        asset.slot_index = payload.slot_index
    session.commit()
    session.refresh(asset)
    return success(asset_response_dummy(asset), "素材更新成功")


def asset_response_dummy(asset: Asset) -> dict:
    return AssetResponse(
        id=asset.id,
        project_id=asset.project_id,
        asset_type=asset.asset_type,
        original_name=asset.original_name,
        display_name=asset.display_name,
        stored_path=asset.stored_path,
        mime_type=asset.mime_type,
        file_size=asset.file_size,
        sha256=asset.sha256,
        width=asset.width,
        height=asset.height,
        slot_index=asset.slot_index,
        created_at=asset.created_at,
        file_url="",
        thumbnail_url="",
    ).model_dump(mode="json")


@router.post("/projects/{project_id}/assets/reorder")
def reorder_assets(project_id: str, payload: ReorderRequest, session: Session = Depends(get_session)):
    project = get_project_or_404(session, project_id)
    clothing = [asset for asset in project.assets if asset.asset_type == "clothing"]
    current_ids = {asset.id for asset in clothing}
    if len(clothing) != 3 or set(payload.asset_ids) != current_ids or len(set(payload.asset_ids)) != 3:
        raise fail("CLOTHING_ASSET_COUNT_INVALID", "必须提供当前项目的三张服装图")
    by_id = {asset.id: asset for asset in clothing}
    # SQLite checks the unique slot constraint during each UPDATE. Move all
    # rows to temporary positions first so a full reorder can safely swap slots.
    for offset, asset in enumerate(clothing):
        asset.slot_index = 100 + offset
    session.flush()
    for index, asset_id in enumerate(payload.asset_ids):
        by_id[asset_id].slot_index = index
    session.commit()
    return success(None, "服装顺序已更新")


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str, request: Request, session: Session = Depends(get_session)):
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise fail("ASSET_NOT_FOUND", "素材不存在", 404)
    path = (request.app.state.settings.data_dir / asset.stored_path).resolve()
    root = request.app.state.settings.data_dir.resolve()
    session.delete(asset)
    session.commit()
    if root in path.parents and path.exists():
        path.unlink()
    return success(None, "素材删除成功")


def asset_file_response(request: Request, asset_id: str) -> FileResponse:
    asset = request.app.state.session_factory()
    try:
        item = asset.get(Asset, asset_id)
        if item is None:
            raise fail("ASSET_NOT_FOUND", "素材不存在", 404)
        path = (request.app.state.settings.data_dir / item.stored_path).resolve()
        root = request.app.state.settings.data_dir.resolve()
        if root not in path.parents or not path.is_file():
            raise fail("ASSET_FILE_NOT_FOUND", "素材文件不存在", 404)
        return FileResponse(path, media_type=item.mime_type, filename=item.original_name)
    finally:
        asset.close()


@router.get("/assets/{asset_id}/file")
def get_asset_file(asset_id: str, request: Request):
    return asset_file_response(request, asset_id)


@router.get("/assets/{asset_id}/thumbnail")
def get_asset_thumbnail(asset_id: str, request: Request):
    return asset_file_response(request, asset_id)


@router.get("/jobs")
def list_jobs(session: Session = Depends(get_session)):
    jobs = session.scalars(select(GenerationJob).order_by(GenerationJob.created_at.desc())).all()
    return success([job_response(job) for job in jobs])


@router.post("/projects/{project_id}/jobs", status_code=status.HTTP_201_CREATED)
def create_job(project_id: str, payload: JobCreate, background_tasks: BackgroundTasks, request: Request, session: Session = Depends(get_session)):
    project = get_project_or_404(session, project_id)
    if any(job.status in {"queued", "validating", "preparing", "submitted", "processing"} for job in project.jobs):
        raise fail("JOB_ALREADY_RUNNING", "当前项目已有任务正在运行")
    clothing = [asset for asset in project.assets if asset.asset_type == "clothing"]
    if not any(asset.asset_type == "model" for asset in project.assets):
        raise fail("MODEL_ASSET_REQUIRED", "请先上传模特图")
    if len(clothing) != 3:
        raise fail("CLOTHING_ASSET_COUNT_INVALID", "请先上传三张服装图")
    if set(payload.clothing_order) != {asset.id for asset in clothing}:
        raise fail("CLOTHING_ORDER_INVALID", "服装顺序必须来自当前项目的三张服装图")
    job = GenerationJob(project_id=project.id, provider=payload.provider, workflow_version="v2" if payload.provider == "agnes" else "v1", status="queued", progress=0, current_node="queued")
    project.status = "generating"
    session.add(job)
    session.commit()
    session.refresh(job)
    background_tasks.add_task(run_job, request.app.state.settings, request.app.state.session_factory, job.id)
    return success(job_response(job), "生成任务已创建")


@router.get("/jobs/{job_id}")
def get_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise fail("JOB_NOT_FOUND", "生成任务不存在", 404)
    return success(job_response(job))


@router.get("/jobs/{job_id}/steps")
def get_job_steps(job_id: str, session: Session = Depends(get_session)):
    if session.get(GenerationJob, job_id) is None:
        raise fail("JOB_NOT_FOUND", "生成任务不存在", 404)
    steps = session.scalars(select(GenerationStep).where(GenerationStep.job_id == job_id).order_by(GenerationStep.id)).all()
    return success([{"id": step.id, "step_key": step.step_key, "attempt": step.attempt, "status": step.status, "provider": step.provider, "model": step.model, "provider_job_id": step.provider_job_id, "progress": step.progress, "error_message": step.error_message, "started_at": step.started_at.isoformat() if step.started_at else None, "finished_at": step.finished_at.isoformat() if step.finished_at else None} for step in steps])


@router.get("/jobs/{job_id}/artifacts")
def get_job_artifacts(job_id: str, request: Request, session: Session = Depends(get_session)):
    if session.get(GenerationJob, job_id) is None:
        raise fail("JOB_NOT_FOUND", "生成任务不存在", 404)
    base = str(request.base_url).rstrip("/")
    artifacts = session.scalars(select(GeneratedArtifact).where(GeneratedArtifact.job_id == job_id).order_by(GeneratedArtifact.created_at)).all()
    return success([{"id": item.id, "job_id": item.job_id, "kind": item.kind, "slot_index": item.slot_index, "relative_path": item.relative_path, "mime_type": item.mime_type, "file_size": item.file_size, "width": item.width, "height": item.height, "duration": item.duration, "file_url": f"{base}/api/artifacts/{item.id}/file"} for item in artifacts])


@router.get("/artifacts/{artifact_id}/file")
def get_artifact_file(artifact_id: str, request: Request, session: Session = Depends(get_session)):
    artifact = session.get(GeneratedArtifact, artifact_id)
    if artifact is None:
        raise fail("ARTIFACT_NOT_FOUND", "中间产物不存在", 404)
    path = (request.app.state.settings.data_dir / artifact.relative_path).resolve()
    if request.app.state.settings.data_dir.resolve() not in path.parents or not path.is_file():
        raise fail("ARTIFACT_FILE_NOT_FOUND", "中间产物文件不存在", 404)
    return FileResponse(path, media_type=artifact.mime_type)





@router.get("/jobs/{job_id}/logs")
def get_job_logs(job_id: str, session: Session = Depends(get_session)):
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise fail("JOB_NOT_FOUND", "生成任务不存在", 404)
    logs = session.scalars(select(WorkflowRun).where(WorkflowRun.job_id == job_id).order_by(WorkflowRun.sequence, WorkflowRun.started_at)).all()
    return success([
        {
            "id": log.id,
            "node_name": log.node_name,
            "sequence": log.sequence,
            "status": log.status,
            "input_summary": log.input_summary,
            "output_summary": log.output_summary,
            "error_message": log.error_message,
            "started_at": log.started_at.isoformat(),
            "finished_at": log.finished_at.isoformat() if log.finished_at else None,
        }
        for log in logs
    ])


@router.get("/jobs/{job_id}/outputs")
def get_job_outputs(job_id: str, request: Request, session: Session = Depends(get_session)):
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise fail("JOB_NOT_FOUND", "生成任务不存在", 404)
    base = str(request.base_url).rstrip("/")
    outputs = session.scalars(select(VideoOutput).where(VideoOutput.job_id == job_id).order_by(VideoOutput.created_at.desc())).all()
    return success([
        {
            "id": output.id,
            "job_id": output.job_id,
            "project_id": output.project_id,
            "video_path": output.video_path,
            "thumbnail_path": output.thumbnail_path,
            "width": output.width,
            "height": output.height,
            "duration": output.duration,
            "file_size": output.file_size,
            "sha256": output.sha256,
            "video_url": f"{base}/api/outputs/{output.id}/video",
            "thumbnail_url": f"{base}/api/outputs/{output.id}/thumbnail",
            "created_at": output.created_at.isoformat(),
        }
        for output in outputs
    ])


def safe_data_file(request: Request, relative_path: str) -> Path:
    root = request.app.state.settings.data_dir.resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise fail("OUTPUT_FILE_NOT_FOUND", "输出文件不存在", 404)
    return path


@router.get("/outputs/{output_id}/video")
def get_output_video(output_id: str, request: Request, session: Session = Depends(get_session)):
    output = session.get(VideoOutput, output_id)
    if output is None:
        raise fail("OUTPUT_NOT_FOUND", "输出不存在", 404)
    return FileResponse(safe_data_file(request, output.video_path), media_type="video/mp4", filename=Path(output.video_path).name)


@router.get("/outputs/{output_id}/thumbnail")
def get_output_thumbnail(output_id: str, request: Request, session: Session = Depends(get_session)):
    output = session.get(VideoOutput, output_id)
    if output is None or not output.thumbnail_path:
        raise fail("OUTPUT_NOT_FOUND", "封面不存在", 404)
    return FileResponse(safe_data_file(request, output.thumbnail_path), media_type="image/png", filename=Path(output.thumbnail_path).name)



@router.get("/backups")
def list_backups(session: Session = Depends(get_session)):
    records = session.scalars(select(BackupRecord).order_by(BackupRecord.created_at.desc())).all()
    return success([
        {
            "id": record.id,
            "archive_name": record.archive_name,
            "archive_path": record.archive_path,
            "manifest_version": record.manifest_version,
            "file_count": record.file_count,
            "file_size": record.file_size,
            "sha256": record.sha256,
            "created_at": record.created_at.isoformat(),
        }
        for record in records
    ])


@router.post("/backups/export", status_code=status.HTTP_201_CREATED)
def export_backup_route(request: Request, session: Session = Depends(get_session)):
    record = export_backup(request.app.state.settings, request.app.state.session_factory)
    return success({"id": record.id, "archive_name": record.archive_name, "file_count": record.file_count, "file_size": record.file_size, "sha256": record.sha256}, "备份创建成功")


@router.get("/backups/{backup_id}/download")
def download_backup(backup_id: str, request: Request, session: Session = Depends(get_session)):
    record = session.get(BackupRecord, backup_id)
    if record is None:
        raise fail("BACKUP_NOT_FOUND", "备份不存在", 404)
    path = safe_data_file(request, record.archive_path)
    return FileResponse(path, media_type="application/zip", filename=record.archive_name)


@router.post("/backups/import", status_code=status.HTTP_201_CREATED)
async def import_backup_route(request: Request, file: UploadFile = File(...), session: Session = Depends(get_session)):
    if not (file.filename or "").lower().endswith(".zip"):
        raise fail("BACKUP_INVALID", "只能导入 ZIP 备份")
    content = await file.read(request.app.state.settings.max_upload_size * 20)
    fd, temporary_name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    Path(temporary_name).write_bytes(content)
    try:
        record = import_backup(request.app.state.settings, request.app.state.session_factory, Path(temporary_name))
    except BackupError as exc:
        raise fail(exc.code, exc.message) from exc
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return success({"id": record.id, "archive_name": record.archive_name, "file_count": record.file_count, "sha256": record.sha256}, "备份导入成功")


@router.post("/backups/{backup_id}/restore")
def restore_backup_route(backup_id: str, request: Request, mode: str = "replace", session: Session = Depends(get_session)):
    record = session.get(BackupRecord, backup_id)
    if record is None:
        raise fail("BACKUP_NOT_FOUND", "备份不存在", 404)
    try:
        session.close()
        restore_backup(request.app.state.settings, request.app.state.session_factory, request.app.state.engine, record, mode=mode)
        engine, session_factory = init_database(request.app.state.settings)
        request.app.state.engine = engine
        request.app.state.session_factory = session_factory
    except BackupError as exc:
        raise fail(exc.code, exc.message) from exc
    return success(None, "备份恢复成功")


@router.delete("/backups/{backup_id}")
def delete_backup(backup_id: str, request: Request, session: Session = Depends(get_session)):
    record = session.get(BackupRecord, backup_id)
    if record is None:
        raise fail("BACKUP_NOT_FOUND", "备份不存在", 404)
    path = (request.app.state.settings.data_dir / record.archive_path).resolve()
    session.delete(record)
    session.commit()
    if path.is_file():
        path.unlink()
    return success(None, "备份删除成功")





@router.get("/dashboard/summary")
def dashboard_summary(session: Session = Depends(get_session)):
    project_count = session.scalar(select(func.count(Project.id))) or 0
    asset_count = session.scalar(select(func.count(Asset.id))) or 0
    job_count = session.scalar(select(func.count(GenerationJob.id))) or 0
    succeeded_count = session.scalar(select(func.count(GenerationJob.id)).where(GenerationJob.status == "succeeded")) or 0
    return success({"project_count": project_count, "asset_count": asset_count, "job_count": job_count, "succeeded_count": succeeded_count})


@router.get("/dashboard/recent-projects")
def recent_projects(session: Session = Depends(get_session)):
    projects = session.scalars(select(Project).order_by(Project.updated_at.desc()).limit(5)).all()
    return success([project_response(project) for project in projects])


@router.get("/dashboard/recent-jobs")
def recent_jobs(session: Session = Depends(get_session)):
    jobs = session.scalars(select(GenerationJob).order_by(GenerationJob.created_at.desc()).limit(8)).all()
    return success([job_response(job) for job in jobs])


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise fail("JOB_NOT_FOUND", "生成任务不存在", 404)
    if job.status in {"succeeded", "failed", "canceled"}:
        raise fail("JOB_CANCEL_FAILED", "当前任务不支持取消")
    job.status = "canceled"
    job.current_node = "canceled"
    job.finished_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(job)
    return success(job_response(job), "任务已取消")


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_201_CREATED)
def retry_job(job_id: str, background_tasks: BackgroundTasks, request: Request, session: Session = Depends(get_session)):
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise fail("JOB_NOT_FOUND", "生成任务不存在", 404)
    if job.status not in {"failed", "canceled"}:
        raise fail("JOB_RETRY_NOT_ALLOWED", "只有失败或已取消任务可以重试")
    project = get_project_or_404(session, job.project_id)
    clothing = sorted((asset for asset in project.assets if asset.asset_type == "clothing"), key=lambda asset: asset.slot_index or 0)
    if len(clothing) != 3 or not any(asset.asset_type == "model" for asset in project.assets):
        raise fail("ASSETS_INCOMPLETE", "项目素材不完整，无法重试")
    replacement = GenerationJob(project_id=project.id, provider=job.provider, workflow_version=job.workflow_version, status="queued", progress=0, current_node="queued")
    project.status = "generating"
    session.add(replacement)
    session.commit()
    session.refresh(replacement)
    background_tasks.add_task(run_job, request.app.state.settings, request.app.state.session_factory, replacement.id)
    return success(job_response(replacement), "已创建重试任务")


@router.post("/jobs/{job_id}/resume", status_code=status.HTTP_200_OK)
def resume_job(job_id: str, background_tasks: BackgroundTasks, request: Request, session: Session = Depends(get_session)):
    """Resume the same job so persisted Agnes step IDs and artifacts can be reused."""
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise fail("JOB_NOT_FOUND", "生成任务不存在", 404)
    if job.status not in {"failed", "canceled"}:
        raise fail("JOB_RESUME_NOT_ALLOWED", "只有失败或已取消任务可以恢复")
    if job.provider not in {"mock", "agnes"}:
        raise fail("PROVIDER_NOT_SUPPORTED", "历史 Provider 不支持恢复")
    project = get_project_or_404(session, job.project_id)
    if any(other.status in {"queued", "validating", "preparing", "submitted", "processing"} for other in project.jobs if other.id != job.id):
        raise fail("JOB_ALREADY_RUNNING", "当前项目已有任务正在运行")
    job.status = "queued"
    job.progress = 0
    job.current_node = "queued"
    job.error_code = None
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    project.status = "generating"
    session.commit()
    session.refresh(job)
    background_tasks.add_task(run_job, request.app.state.settings, request.app.state.session_factory, job.id)
    return success(job_response(job), "已恢复原任务，已有中间产物将优先复用")


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, request: Request, session: Session = Depends(get_session)):
    job = session.get(GenerationJob, job_id)
    if job is None:
        raise fail("JOB_NOT_FOUND", "生成任务不存在", 404)
    job_dir = request.app.state.settings.projects_dir / job.project_id / "jobs" / job_id
    output_dir = request.app.state.settings.projects_dir / job.project_id / "outputs" / job_id
    session.delete(job)
    session.commit()
    for directory in (job_dir, output_dir):
        if directory.exists():
            shutil.rmtree(directory)
    return success(None, "任务删除成功")


@router.delete("/outputs/{output_id}")
def delete_output(output_id: str, request: Request, session: Session = Depends(get_session)):
    output = session.get(VideoOutput, output_id)
    if output is None:
        raise fail("OUTPUT_NOT_FOUND", "输出不存在", 404)
    video_path = (request.app.state.settings.data_dir / output.video_path).resolve()
    thumbnail_path = (request.app.state.settings.data_dir / output.thumbnail_path).resolve() if output.thumbnail_path else None
    session.delete(output)
    session.commit()
    for path in (video_path, thumbnail_path):
        if path and path.is_file():
            path.unlink()
    return success(None, "输出已删除")


@router.get("/providers")
def providers(request: Request):
    try:
        AgnesImageProvider(request.app.state.settings).validate_config()
        agnes_configured = True
        agnes_description = "已配置 Agnes 双模型，可执行三图换装和两段首尾帧视频"
    except AgnesNotConfigured:
        agnes_configured = False
        agnes_description = "请在项目根目录 .env 设置 AGNES_API_KEY"
    return success([
        {"name": "mock", "label": "演示 Provider", "configured": True, "description": "本地生成可播放演示视频"},
        {"name": "agnes", "label": "Agnes AI", "configured": agnes_configured, "description": agnes_description},
    ])


@router.post("/providers/{provider}/validate")
def validate_provider(provider: str, request: Request):
    if provider == "mock":
        return success({"provider": provider, "configured": True}, "Provider 配置有效")
    if provider == "agnes":
        try:
            AgnesImageProvider(request.app.state.settings).validate_config()
        except AgnesNotConfigured as exc:
            return success({"provider": provider, "configured": False}, str(exc))
        return success({"provider": provider, "configured": True}, "Agnes API Key 已配置")
    raise fail("PROVIDER_NOT_SUPPORTED", "不支持的 Provider", 400)


@router.get("/settings")
def get_settings_route(session: Session = Depends(get_session)):
    settings = session.scalars(select(AppSetting)).all()
    values = {item.key: json.loads(item.value_json) for item in settings}
    return success(values)


@router.patch("/settings")
def patch_settings(payload: dict, session: Session = Depends(get_session)):
    for key, value in payload.items():
        if key in {"api_key", "agnes_api_key", "AGNES_API_KEY"}:
            continue
        setting = session.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key, value_json=json.dumps(value, ensure_ascii=False))
            session.add(setting)
        else:
            setting.value_json = json.dumps(value, ensure_ascii=False)
    session.commit()
    return get_settings_route(session)
