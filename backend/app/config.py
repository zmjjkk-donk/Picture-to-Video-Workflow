from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """Runtime paths and safe, non-secret application settings."""

    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    database_name: str = "app.db"
    max_upload_size: int = 20 * 1024 * 1024
    app_name: str = "电商服装 AI 换装短视频工作流"
    app_version: str = "0.1.0"
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "Wan-AI/Wan2.2-I2V-A14B"
    siliconflow_poll_interval_seconds: float = 5.0
    siliconflow_poll_attempts: int = 60

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_name

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Build settings from environment without storing secrets in SQLite."""

    data_dir = Path(os.getenv("APP_DATA_DIR", str(PROJECT_ROOT / "data")))
    return Settings(
        data_dir=data_dir,
        siliconflow_api_key=os.getenv("SILICONFLOW_API_KEY", "").strip(),
        siliconflow_base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/"),
        siliconflow_model=os.getenv("SILICONFLOW_VIDEO_MODEL", "Wan-AI/Wan2.2-I2V-A14B").strip(),
        siliconflow_poll_interval_seconds=float(os.getenv("SILICONFLOW_POLL_INTERVAL_SECONDS", "5")),
        siliconflow_poll_attempts=int(os.getenv("SILICONFLOW_POLL_ATTEMPTS", "60")),
    )
