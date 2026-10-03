from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_local_env() -> None:
    """Load the project .env without overwriting explicitly exported values."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    """Runtime paths and safe, non-secret application settings."""

    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    database_name: str = "app.db"
    max_upload_size: int = 20 * 1024 * 1024
    app_name: str = "电商服装 AI 换装短视频工作流"
    app_version: str = "0.1.0"
    agnes_api_key: str = ""
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    agnes_video_status_url: str = "https://apihub.agnes-ai.com/agnesapi"
    agnes_image_model: str = "agnes-image-2.0-flash"
    agnes_video_model: str = "agnes-video-2.5-flash"
    agnes_image_size: str = "768x1024"
    agnes_video_size: str = "720P"
    agnes_video_aspect_ratio: str = "9:16"
    agnes_segment_seconds: str = "4"
    agnes_image_timeout_seconds: float = 360.0
    agnes_poll_interval_seconds: float = 2.0
    agnes_video_timeout_seconds: float = 1200.0

    def __post_init__(self) -> None:
        # Uploads and generated files use absolute paths when calculating
        # portable paths relative to the data directory. Normalize once so
        # APP_DATA_DIR=data also works and stays stable if the cwd changes.
        object.__setattr__(self, "data_dir", self.data_dir.expanduser().resolve())

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

    _load_local_env()
    data_dir = Path(os.getenv("APP_DATA_DIR", str(PROJECT_ROOT / "data")))
    return Settings(
        data_dir=data_dir,
        agnes_api_key=os.getenv("AGNES_API_KEY", "").strip(),
        agnes_base_url=os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1").rstrip("/"),
        agnes_video_status_url=os.getenv("AGNES_VIDEO_STATUS_URL", "https://apihub.agnes-ai.com/agnesapi").rstrip("/"),
        agnes_image_model=os.getenv("AGNES_IMAGE_MODEL", "agnes-image-2.0-flash").strip(),
        agnes_video_model=os.getenv("AGNES_VIDEO_MODEL", "agnes-video-2.5-flash").strip(),
        agnes_image_size=os.getenv("AGNES_IMAGE_SIZE", "768x1024").strip(),
        agnes_video_size=os.getenv("AGNES_VIDEO_SIZE", "720P").strip(),
        agnes_video_aspect_ratio=os.getenv("AGNES_VIDEO_ASPECT_RATIO", "9:16").strip(),
        agnes_segment_seconds=os.getenv("AGNES_SEGMENT_SECONDS", "4").strip(),
        agnes_image_timeout_seconds=float(os.getenv("AGNES_IMAGE_TIMEOUT_SECONDS", "360")),
        agnes_poll_interval_seconds=float(os.getenv("AGNES_POLL_INTERVAL_SECONDS", "2")),
        agnes_video_timeout_seconds=float(os.getenv("AGNES_VIDEO_TIMEOUT_SECONDS", "1200")),
    )
