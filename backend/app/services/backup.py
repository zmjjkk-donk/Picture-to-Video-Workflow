from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from ..config import Settings
from ..models import BackupRecord, Project


class BackupError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project_manifest(settings: Settings, session_factory, project: Project) -> None:
    project_dir = settings.projects_dir / project.id
    project_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v1",
        "project_id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "video_ratio": project.video_ratio,
        "duration_seconds": project.duration_seconds,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }
    (project_dir / "project.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _backup_files(settings: Settings) -> list[Path]:
    if not settings.data_dir.exists():
        return []
    backup_root = settings.backups_dir.resolve()
    return [
        path
        for path in settings.data_dir.rglob("*")
        if path.is_file() and backup_root not in path.resolve().parents
    ]


def export_backup(settings: Settings, session_factory) -> BackupRecord:
    settings.ensure_directories()
    with session_factory() as session:
        projects = session.scalars(select(Project)).all()
        for project in projects:
            project_manifest(settings, session_factory, project)
    files = _backup_files(settings)
    archive_name = f"backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}.zip"
    archive_path = settings.backups_dir / archive_name
    manifest_files = []
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(settings.data_dir).as_posix()
            archive.write(path, relative)
            manifest_files.append({"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path)})
        manifest = {
            "version": "v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "project_ids": [project.id for project in projects],
            "files": manifest_files,
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    record = BackupRecord(archive_name=archive_name, archive_path=str(archive_path.relative_to(settings.data_dir)).replace("\\", "/"), manifest_version="v1", file_count=len(manifest_files) + 1, file_size=archive_path.stat().st_size, sha256=sha256_file(archive_path))
    with session_factory() as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def validate_archive(archive_path: Path) -> dict:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            for name in names:
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    raise BackupError("BACKUP_INVALID", "备份包含非法路径")
            if "manifest.json" not in names:
                raise BackupError("BACKUP_INVALID", "备份缺少 manifest.json")
            manifest = json.loads(archive.read("manifest.json"))
            for item in manifest.get("files", []):
                if item["path"] not in names:
                    raise BackupError("BACKUP_INVALID", f"备份缺少文件：{item['path']}")
                content = archive.read(item["path"])
                if len(content) != item["size"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
                    raise BackupError("BACKUP_CHECKSUM_MISMATCH", f"文件校验失败：{item['path']}")
            return manifest
    except zipfile.BadZipFile as exc:
        raise BackupError("BACKUP_INVALID", "文件不是有效 ZIP 备份") from exc


def import_backup(settings: Settings, session_factory, source_path: Path) -> BackupRecord:
    settings.ensure_directories()
    manifest = validate_archive(source_path)
    archive_name = f"import-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}.zip"
    destination = settings.backups_dir / archive_name
    shutil.copy2(source_path, destination)
    record = BackupRecord(archive_name=archive_name, archive_path=str(destination.relative_to(settings.data_dir)).replace("\\", "/"), manifest_version=manifest.get("version", "v1"), file_count=len(manifest.get("files", [])) + 1, file_size=destination.stat().st_size, sha256=sha256_file(destination))
    with session_factory() as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def restore_backup(settings: Settings, session_factory, engine, record: BackupRecord, mode: str = "replace") -> None:
    if mode != "replace":
        raise BackupError("BACKUP_PROJECT_CONFLICT", "当前版本只允许显式 replace 模式恢复")
    archive_path = (settings.data_dir / record.archive_path).resolve()
    if not archive_path.is_file():
        raise BackupError("BACKUP_INVALID", "备份文件不存在")
    validate_archive(archive_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="workflow-restore-"))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temp_dir)
        if not (temp_dir / "app.db").is_file():
            raise BackupError("BACKUP_INVALID", "备份缺少 app.db")
        engine.dispose()
        for name in ("app.db", "workflow_checkpoints.db"):
            target = settings.data_dir / name
            if target.exists():
                target.unlink()
            source = temp_dir / name
            if source.exists():
                shutil.copy2(source, target)
        source_projects = temp_dir / "projects"
        if source_projects.exists():
            if settings.projects_dir.exists():
                shutil.rmtree(settings.projects_dir)
            shutil.copytree(source_projects, settings.projects_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
