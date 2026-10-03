from pathlib import Path

import httpx
import pytest

from backend.app.config import Settings
from backend.app.providers.agnes_common import AgnesError, AgnesNotConfigured, extract_token_usage
from backend.app.providers.agnes_image import AgnesImageProvider
from backend.app.providers.agnes_video import AgnesVideoProvider


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", agnes_api_key="test-key")


def test_agnes_image_request_uses_two_data_uri_images_and_nested_response_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    model = tmp_path / "model.png"
    clothing = tmp_path / "clothing.png"
    model.write_bytes(b"model")
    clothing.write_bytes(b"clothing")
    calls: list[dict] = []

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(200, json={"data": [{"b64_json": "aW1hZ2U=", "url": None}]}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    output = tmp_path / "outfit.png"
    remote = AgnesImageProvider(_settings(tmp_path)).generate_outfit_image(model, clothing, "保持模特身份，只替换服装", output)
    assert remote is None
    assert output.read_bytes() == b"image"
    payload = calls[0]["json"]
    assert payload["model"] == "agnes-image-2.0-flash"
    assert payload["extra_body"]["response_format"] == "url"
    assert len(payload["extra_body"]["image"]) == 2
    assert all(item.startswith("data:image/png;base64,") for item in payload["extra_body"]["image"])


def test_agnes_video_keyframe_submission_and_status_use_documented_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        if method == "POST":
            return httpx.Response(200, json={"video_id": "video-123"}, request=httpx.Request(method, url))
        return httpx.Response(200, json={"status": "completed", "progress": 100, "url": "https://example.test/video.mp4"}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    provider = AgnesVideoProvider(_settings(tmp_path))
    video_id = provider.submit_keyframe_job("https://example.test/a.png", "https://example.test/b.png", "自然从A换装到B")
    status, progress, _ = provider.get_status(video_id)
    assert video_id == "video-123"
    assert status == "succeeded"
    assert progress == 100
    submit = calls[0]
    assert submit["url"].endswith("/v1/videos")
    assert submit["json"]["mode"] == "keyframe"
    assert submit["json"]["first_frame"].endswith("a.png")
    assert submit["json"]["last_frame"].endswith("b.png")
    poll = calls[1]
    assert "/agnesapi?" in poll["url"]
    assert "model_name=agnes-video-2.5-flash" in poll["url"]


def test_placeholder_key_is_rejected_without_network(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data", agnes_api_key="YOUR_AGNES_API_KEY_HERE")
    with pytest.raises(AgnesNotConfigured):
        AgnesImageProvider(settings).validate_config()


def test_token_usage_is_normalized_only_when_provider_returns_it():
    usage = extract_token_usage({"usage": {"prompt_tokens": 12, "completion_tokens": 8}})
    assert usage == {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20, "raw_usage_json": '{"completion_tokens": 8, "prompt_tokens": 12}'}
    assert extract_token_usage({"data": [{"url": "https://example.test/image.png"}]}) is None


def test_provider_exposes_reported_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    model = tmp_path / "model.png"
    clothing = tmp_path / "clothing.png"
    model.write_bytes(b"model")
    clothing.write_bytes(b"clothing")

    def fake_request(method, url, **kwargs):
        return httpx.Response(200, json={"usage": {"input_tokens": 3, "output_tokens": 7}, "data": [{"b64_json": "aW1hZ2U="}]}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    provider = AgnesImageProvider(_settings(tmp_path))
    provider.generate_outfit_image(model, clothing, "prompt", tmp_path / "output.png")
    assert provider.last_usage is not None
    assert provider.last_usage["total_tokens"] == 10


@pytest.mark.parametrize(("status_code", "code"), [(401, "AGNES_AUTH_FAILED"), (429, "AGNES_RATE_LIMITED")])
def test_agnes_http_errors_are_actionable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status_code: int, code: str):
    def fake_request(method, url, **kwargs):
        return httpx.Response(status_code, json={"message": "provider error"}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    with pytest.raises(AgnesError) as error:
        AgnesVideoProvider(_settings(tmp_path)).submit_keyframe_job("https://example.test/a.png", "https://example.test/b.png", "prompt")
    assert error.value.code == code
