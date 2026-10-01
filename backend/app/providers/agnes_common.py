from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from urllib.parse import urlencode

import httpx

from ..config import Settings


class AgnesError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class AgnesNotConfigured(AgnesError):
    def __init__(self, message: str = "Agnes API Key 未配置，请设置 AGNES_API_KEY"):
        super().__init__("KEY_NOT_CONFIGURED", message)


class AgnesClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def validate_config(self) -> None:
        key = self.settings.agnes_api_key
        if not key or key == "YOUR_AGNES_API_KEY_HERE":
            raise AgnesNotConfigured()

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.agnes_api_key}", "Content-Type": "application/json"}

    def request_json(self, method: str, url: str, *, json: dict | None = None, params: dict | None = None, timeout: float = 60.0) -> dict:
        self.validate_config()
        try:
            response = httpx.request(method, url, headers=self.headers, json=json, params=params, timeout=timeout)
        except httpx.HTTPError as exc:
            raise AgnesError("AGNES_NETWORK_ERROR", f"Agnes 网络请求失败：{exc}") from exc
        if response.status_code in {401, 403}:
            raise AgnesError("AGNES_AUTH_FAILED", "Agnes API Key 无效或无权访问该模型")
        if response.status_code == 429:
            raise AgnesError("AGNES_RATE_LIMITED", "Agnes 请求频率或额度受限")
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail") or response.json().get("message") or response.text
            except ValueError:
                detail = response.text
            raise AgnesError("AGNES_REQUEST_FAILED", f"Agnes 请求失败（{response.status_code}）：{detail}")
        try:
            body = response.json()
        except ValueError as exc:
            raise AgnesError("AGNES_INVALID_RESPONSE", "Agnes 返回内容不是 JSON") from exc
        if not isinstance(body, dict):
            raise AgnesError("AGNES_INVALID_RESPONSE", "Agnes 返回结构不是对象")
        return body

    @staticmethod
    def data_url(path: Path) -> str:
        if not path.is_file():
            raise AgnesError("INPUT_FILE_NOT_FOUND", f"输入文件不存在：{path}")
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @staticmethod
    def extract_error(body: dict) -> str:
        return str(body.get("error") or body.get("message") or body.get("detail") or "Agnes 未提供错误原因")

    @staticmethod
    def status_url(base_url: str, video_id: str, model_name: str) -> str:
        return f"{base_url}?{urlencode({'video_id': video_id, 'model_name': model_name})}"
