from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.providers.mock import MockVideoProvider
from backend.app.models import GeneratedArtifact, GenerationJob, GenerationStep


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    from io import BytesIO

    stream = BytesIO()
    Image.new("RGB", (120, 200), color).save(stream, format="PNG")
    return stream.getvalue()


def test_agnes_workflow_runs_three_images_two_videos_and_composes_output(tmp_path: Path, monkeypatch):
    class FakeImageProvider:
        name = "agnes-image"

        def __init__(self, settings):
            self.calls = []

        def generate_outfit_image(self, model_path, clothing_path, prompt, output_path):
            self.calls.append((model_path, clothing_path))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (120, 200), (40 + len(self.calls) * 30, 80, 140)).save(output_path)
            return f"https://public.example/look-{len(self.calls)}.png"

    class FakeVideoProvider:
        name = "agnes-video"
        pairs: list[tuple[str, str]] = []
        counter = 0

        def __init__(self, settings):
            self.mock = MockVideoProvider()

        def submit_keyframe_job(self, first_frame_url, last_frame_url, prompt):
            self.pairs.append((first_frame_url, last_frame_url))
            self.counter += 1
            return f"video-{self.counter}"

        def get_status(self, video_id):
            return "succeeded", 100, "ok"

        def download_video(self, video_id, output_path):
            request = self.mock.submit_video_job(type("Request", (), {"duration_seconds": 1})())
            result = self.mock.download_video(request, output_path.parent)
            output_path.write_bytes(result.video_path.read_bytes())
            result.video_path.unlink(missing_ok=True)
            return "https://public.example/video.mp4"

    monkeypatch.setattr("backend.app.workflow.runner.AgnesImageProvider", FakeImageProvider)
    monkeypatch.setattr("backend.app.workflow.runner.AgnesVideoProvider", FakeVideoProvider)
    settings = Settings(data_dir=tmp_path / "data", agnes_api_key="test-key", agnes_poll_interval_seconds=0, agnes_video_timeout_seconds=5)
    client = TestClient(create_app(settings))
    project = client.post("/api/projects", json={"name": "Agnes 流程测试"}).json()["data"]
    project_id = project["id"]
    client.post(f"/api/projects/{project_id}/assets/model", files={"file": ("model.png", _png_bytes((200, 180, 160)), "image/png")})
    for slot, color in enumerate(((220, 60, 60), (60, 180, 80), (60, 90, 220))):
        client.post(f"/api/projects/{project_id}/assets/clothing", params={"slot_index": slot, "name": f"服装{slot + 1}"}, files={"file": (f"look{slot}.png", _png_bytes(color), "image/png")})
    assets = client.get(f"/api/projects/{project_id}/assets").json()["data"]
    clothing_ids = [item["id"] for item in assets if item["asset_type"] == "clothing"]
    response = client.post(f"/api/projects/{project_id}/jobs", json={"provider": "agnes", "clothing_order": clothing_ids})
    assert response.status_code == 201
    job_id = response.json()["data"]["id"]
    job = client.get(f"/api/jobs/{job_id}").json()["data"]
    assert job["status"] == "succeeded", {"error_code": job.get("error_code"), "error_message": job.get("error_message"), "current_node": job.get("current_node")}
    assert client.get(f"/api/jobs/{job_id}/steps").json()["data"]
    artifacts = client.get(f"/api/jobs/{job_id}/artifacts").json()["data"]
    assert {artifact["kind"] for artifact in artifacts} == {"outfit_image", "transition_video", "final_video", "cover"}
    assert len([artifact for artifact in artifacts if artifact["kind"] == "outfit_image"]) == 3
    assert len([artifact for artifact in artifacts if artifact["kind"] == "transition_video"]) == 2
    outputs = client.get(f"/api/jobs/{job_id}/outputs").json()["data"]
    assert len(outputs) == 1
    assert client.get(outputs[0]["video_url"]).status_code == 200
