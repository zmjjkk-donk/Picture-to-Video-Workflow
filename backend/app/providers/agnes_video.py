from __future__ import annotations

from pathlib import Path

import httpx

from ..config import Settings
from .agnes_common import AgnesClient, AgnesError


class AgnesVideoProvider(AgnesClient):
    name = "agnes-video"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        self._video_urls: dict[str, str] = {}

    def submit_keyframe_job(self, first_frame_url: str | None, last_frame_url: str | None, prompt: str) -> str:
        if not first_frame_url or not last_frame_url:
            raise AgnesError("FRAME_URL_UNAVAILABLE", "首尾帧必须是 Agnes 可访问的公网 URL")
        body = self.request_json(
            "POST",
            f"{self.settings.agnes_base_url}/videos",
            json={
                "model": self.settings.agnes_video_model,
                "prompt": prompt,
                "seconds": self.settings.agnes_segment_seconds,
                "mode": "keyframe",
                "size": self.settings.agnes_video_size,
                "aspect_ratio": self.settings.agnes_video_aspect_ratio,
                "n": 1,
                "first_frame": first_frame_url,
                "last_frame": last_frame_url,
            },
            timeout=60.0,
        )
        video_id = body.get("video_id")
        if not video_id:
            raise AgnesError("VIDEO_SUBMIT_UNKNOWN", f"Agnes 视频提交未返回 video_id：{body}")
        return str(video_id)

    def get_status(self, video_id: str) -> tuple[str, int, str]:
        url = self.status_url(self.settings.agnes_video_status_url, video_id, self.settings.agnes_video_model)
        body = self.request_json("GET", url, timeout=60.0)
        status = str(body.get("status", "")).lower()
        progress = int(body.get("progress") or 0)
        if status == "completed":
            remote_url = body.get("url")
            if not remote_url:
                raise AgnesError("VIDEO_GENERATION_FAILED", "Agnes 已完成但没有返回视频 URL")
            self._video_urls[video_id] = str(remote_url)
            return "succeeded", 100, "Agnes 视频生成完成"
        if status == "failed":
            raise AgnesError("VIDEO_GENERATION_FAILED", str(body.get("error") or "Agnes 视频生成失败"))
        return "processing", max(1, min(progress, 99)), str(body.get("status") or "等待 Agnes 视频任务")

    def download_video(self, video_id: str, output_path: Path) -> str:
        remote_url = self._video_urls.get(video_id)
        if not remote_url:
            raise AgnesError("MEDIA_DOWNLOAD_FAILED", "视频 URL 尚未返回")
        try:
            response = httpx.get(remote_url, timeout=180.0)
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)
        except (httpx.HTTPError, OSError) as exc:
            raise AgnesError("MEDIA_DOWNLOAD_FAILED", f"Agnes 视频下载失败：{exc}") from exc
        return remote_url
