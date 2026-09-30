import time
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.providers.base import VideoJobRequest
from backend.app.providers.mock import MockVideoProvider
from backend.app.providers.siliconflow import ProviderNotConfigured, SiliconFlowVideoProvider


def image_bytes(color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (40, 60), color)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def prepare_project(client: TestClient) -> tuple[str, list[str]]:
    project_id = client.post("/api/projects", json={"name": "工作流测试项目"}).json()["data"]["id"]
    client.post(f"/api/projects/{project_id}/assets/model", files={"file": ("model.png", image_bytes((20, 30, 40)), "image/png")})
    clothing_ids = []
    for index in range(3):
        response = client.post(
            f"/api/projects/{project_id}/assets/clothing",
            data={"name": f"服装 {index + 1}", "slot_index": str(index)},
            files={"file": (f"cloth-{index}.png", image_bytes((index * 40, 80, 120)), "image/png")},
        )
        clothing_ids.append(response.json()["data"]["id"])
    return project_id, clothing_ids


def test_mock_provider_creates_valid_vertical_mp4(tmp_path: Path):
    provider = MockVideoProvider()
    output_dir = tmp_path / "output"
    request = VideoJobRequest(job_id="job-1", prompt="demo", output_dir=output_dir, duration_seconds=1)
    provider_job_id = provider.submit_video_job(request)
    assert provider.get_video_job_status(provider_job_id).status == "processing"
    assert provider.get_video_job_status(provider_job_id).status == "processing"
    assert provider.get_video_job_status(provider_job_id).status == "succeeded"
    result = provider.download_video(provider_job_id, output_dir)
    assert result.video_path.exists()
    assert result.thumbnail_path.exists()
    assert result.video_path.read_bytes()[4:8] == b"ftyp"
    assert (result.width, result.height) == (360, 640)


def test_langgraph_job_persists_output_logs_and_checkpoint(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data")
    client = TestClient(create_app(settings))
    project_id, clothing_ids = prepare_project(client)

    response = client.post(f"/api/projects/{project_id}/jobs", json={"provider": "mock", "clothing_order": clothing_ids})
    assert response.status_code == 201
    job_id = response.json()["data"]["id"]

    deadline = time.time() + 15
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()["data"]
        if job["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.1)
    assert job is not None
    assert job["status"] == "succeeded", job
    assert job["progress"] == 100
    assert (settings.data_dir / "workflow_checkpoints.db").exists()

    logs = client.get(f"/api/jobs/{job_id}/logs").json()["data"]
    assert [log["node_name"] for log in logs] == ["validate_assets", "validate_assets", "prepare_prompt", "submit_video_job", "poll_video_job", "save_output"]
    assert all(log["status"] in {"running", "succeeded"} for log in logs)

    outputs = client.get(f"/api/jobs/{job_id}/outputs").json()["data"]
    assert len(outputs) == 1
    output = outputs[0]
    assert output["width"] == 360
    assert output["height"] == 640
    video = client.get(output["video_url"])
    assert video.status_code == 200
    assert video.content[4:8] == b"ftyp"
    thumbnail = client.get(output["thumbnail_url"])
    assert thumbnail.status_code == 200
    assert thumbnail.content.startswith(b"\x89PNG")


def test_siliconflow_provider_is_explicitly_unconfigured():
    provider = SiliconFlowVideoProvider()
    try:
        provider.validate_config()
    except ProviderNotConfigured as exc:
        assert "API Key" in str(exc)
    else:
        raise AssertionError("未配置 Provider 不应被视为已配置")
