from __future__ import annotations

import base64
from pathlib import Path

import httpx

from ..config import Settings
from .agnes_common import AgnesClient, AgnesError


class AgnesImageProvider(AgnesClient):
    name = "agnes-image"

    def generate_outfit_image(self, model_path: Path, clothing_path: Path, prompt: str, output_path: Path) -> str | None:
        body = self.request_json(
            "POST",
            f"{self.settings.agnes_base_url}/images/generations",
            json={
                "model": self.settings.agnes_image_model,
                "prompt": prompt,
                "size": self.settings.agnes_image_size,
                "extra_body": {
                    "image": [self.data_url(model_path), self.data_url(clothing_path)],
                    "response_format": "url",
                },
            },
            timeout=self.settings.agnes_image_timeout_seconds,
        )
        items = body.get("data") or []
        if not items or not isinstance(items[0], dict):
            raise AgnesError("IMAGE_GENERATION_FAILED", f"Agnes 生图未返回 data：{body}")
        item = items[0]
        remote_url = item.get("url")
        encoded = item.get("b64_json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if remote_url:
            try:
                response = httpx.get(str(remote_url), timeout=120.0)
                response.raise_for_status()
                output_path.write_bytes(response.content)
            except (httpx.HTTPError, OSError) as exc:
                raise AgnesError("MEDIA_DOWNLOAD_FAILED", f"换装图下载失败：{exc}") from exc
            return str(remote_url)
        if encoded:
            try:
                output_path.write_bytes(base64.b64decode(encoded))
            except (ValueError, OSError) as exc:
                raise AgnesError("IMAGE_GENERATION_FAILED", "Agnes 返回的 Base64 图片无法解析") from exc
            return None
        raise AgnesError("IMAGE_GENERATION_FAILED", "Agnes 生图没有返回 url 或 b64_json")
