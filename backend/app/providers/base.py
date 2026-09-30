from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class VideoJobRequest:
    job_id: str
    prompt: str
    output_dir: Path
    duration_seconds: int = 5
    video_ratio: str = "9:16"
    image_path: Path | None = None
    reference_image_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ProviderStatus:
    status: str
    progress: int
    message: str = ""


@dataclass(frozen=True)
class VideoDownload:
    video_path: Path
    thumbnail_path: Path
    width: int
    height: int
    duration: float


class VideoProvider(Protocol):
    name: str

    def validate_config(self) -> None: ...

    def submit_video_job(self, request: VideoJobRequest) -> str: ...

    def get_video_job_status(self, provider_job_id: str) -> ProviderStatus: ...

    def download_video(self, provider_job_id: str, output_dir: Path) -> VideoDownload: ...

    def cancel_video_job(self, provider_job_id: str) -> None: ...
