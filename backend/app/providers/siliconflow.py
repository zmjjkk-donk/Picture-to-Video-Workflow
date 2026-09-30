from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import httpx
import imageio.v2 as imageio
from PIL import Image

from ..config import Settings
from .base import ProviderStatus, VideoDownload, VideoJobRequest


class ProviderNotConfigured(RuntimeError):
    pass


class SiliconFlowRequestError(RuntimeError):
    pass


class SiliconFlowVideoProvider:
    """SiliconFlow Wan image-to-video provider.

    The current SiliconFlow video endpoint accepts one input image. The
    workflow sends the model image as the I2V image and keeps clothing assets
    as references for a future virtual-try-on preprocessing node.
    """

    name = "siliconflow"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._video_urls: dict[str, str] = {}

    def validate_config(self) -> None:
        if not self.settings.siliconflow_api_key:
            raise ProviderNotConfigured("SiliconFlow API Key 未配置，请设置 SILICONFLOW_API_KEY")
        if not self.settings.siliconflow_model:
            raise ProviderNotConfigured("SiliconFlow 视频模型未配置")

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.siliconflow_api_key}", "Content-Type": "application/json"}

    def _post(self, path: str, payload: dict) -> dict:
        try:
            response = httpx.post(f"{self.settings.siliconflow_base_url}{path}", headers=self._headers, json=payload, timeout=60.0)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("message", exc.response.text)
            except ValueError:
                detail = exc.response.text
            raise SiliconFlowRequestError(f"SiliconFlow 请求失败（{exc.response.status_code}）：{detail}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise SiliconFlowRequestError(f"SiliconFlow 网络或响应错误：{exc}") from exc
        if not isinstance(body, dict):
            raise SiliconFlowRequestError("SiliconFlow 返回格式不是 JSON 对象")
        return body

    @staticmethod
    def _image_size(video_ratio: str) -> str:
        return {"16:9": "1280x720", "1:1": "960x960", "9:16": "720x1280"}.get(video_ratio, "720x1280")

    @staticmethod
    def _data_url(path: Path) -> str:
        if not path.is_file():
            raise SiliconFlowRequestError(f"输入图片不存在：{path}")
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    def submit_video_job(self, request: VideoJobRequest) -> str:
        self.validate_config()
        if request.image_path is None:
            raise SiliconFlowRequestError("SiliconFlow 图生视频需要模特图片")
        body = self._post("/video/submit", {"model": self.settings.siliconflow_model, "prompt": request.prompt, "image_size": self._image_size(request.video_ratio), "image": self._data_url(request.image_path)})
        request_id = body.get("requestId")
        if not request_id:
            raise SiliconFlowRequestError(f"SiliconFlow 未返回 requestId：{body}")
        return str(request_id)

    def get_video_job_status(self, provider_job_id: str) -> ProviderStatus:
        self.validate_config()
        body = self._post("/video/status", {"requestId": provider_job_id})
        status = str(body.get("status", "")).lower()
        if status == "succeed":
            videos = (body.get("results") or {}).get("videos") or []
            if videos and videos[0].get("url"):
                self._video_urls[provider_job_id] = str(videos[0]["url"])
            return ProviderStatus("succeeded", 100, body.get("reason", "SiliconFlow 视频生成完成"))
        if status in {"inqueue", "in_queue", "inprogress", "in_progress"}:
            return ProviderStatus("processing", 60, body.get("reason", "SiliconFlow 正在生成视频"))
        if status == "failed":
            return ProviderStatus("failed", 0, body.get("reason", "SiliconFlow 视频生成失败"))
        return ProviderStatus("processing", 50, body.get("reason", "等待 SiliconFlow 返回任务状态"))

    def download_video(self, provider_job_id: str, output_dir: Path) -> VideoDownload:
        video_url = self._video_urls.get(provider_job_id)
        if not video_url:
            raise SiliconFlowRequestError("视频地址尚未返回，请继续轮询任务状态")
        output_dir.mkdir(parents=True, exist_ok=True)
        video_path = output_dir / "siliconflow-outfit-change.mp4"
        thumbnail_path = output_dir / "siliconflow-outfit-change.png"
        try:
            response = httpx.get(video_url, timeout=120.0)
            response.raise_for_status()
            video_path.write_bytes(response.content)
            reader = imageio.get_reader(video_path)
            meta = reader.get_meta_data()
            first_frame = reader.get_data(0)
            reader.close()
            Image.fromarray(first_frame).save(thumbnail_path, format="PNG")
        except (httpx.HTTPError, OSError, ValueError, IndexError) as exc:
            raise SiliconFlowRequestError(f"下载 SiliconFlow 视频失败：{exc}") from exc
        width, height = meta.get("size", (720, 1280))
        duration = float(meta.get("duration") or 0)
        return VideoDownload(video_path=video_path, thumbnail_path=thumbnail_path, width=int(width), height=int(height), duration=duration)

    def cancel_video_job(self, provider_job_id: str) -> None:
        self._video_urls.pop(provider_job_id, None)
