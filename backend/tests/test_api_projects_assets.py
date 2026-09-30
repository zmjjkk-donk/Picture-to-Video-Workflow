from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.app.config import Settings
from backend.app.main import create_app


def image_bytes(color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (40, 60), color)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def make_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path / "data")))


def create_project(client: TestClient) -> str:
    response = client.post("/api/projects", json={"name": "测试项目", "description": "素材 API 测试"})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def test_create_project_upload_assets_reorder_and_read_file(tmp_path: Path):
    client = make_client(tmp_path)
    project_id = create_project(client)

    model = client.post("/api/projects/%s/assets/model" % project_id, files={"file": ("model.png", image_bytes((20, 30, 40)), "image/png")})
    assert model.status_code == 201
    assert model.json()["data"]["asset_type"] == "model"

    clothing_ids = []
    for index, name in enumerate(["白色针织衫", "蓝色风衣", "黑色西装"]):
        response = client.post(
            f"/api/projects/{project_id}/assets/clothing",
            data={"name": name, "slot_index": str(index)},
            files={"file": (f"cloth-{index}.png", image_bytes((index * 40, 80, 120)), "image/png")},
        )
        assert response.status_code == 201
        clothing_ids.append(response.json()["data"]["id"])

    detail = client.get(f"/api/projects/{project_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "ready"
    assert detail.json()["data"]["asset_count"] == 4

    reordered = client.post(f"/api/projects/{project_id}/assets/reorder", json={"asset_ids": list(reversed(clothing_ids))})
    assert reordered.status_code == 200
    assets = client.get(f"/api/projects/{project_id}/assets").json()["data"]
    clothing = [asset for asset in assets if asset["asset_type"] == "clothing"]
    assert [asset["id"] for asset in clothing] == list(reversed(clothing_ids))
    assert [asset["slot_index"] for asset in clothing] == [0, 1, 2]

    file_response = client.get(model.json()["data"]["file_url"])
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "image/png"
    assert file_response.content.startswith(b"\x89PNG")


def test_asset_validation_and_job_requires_complete_assets(tmp_path: Path):
    client = make_client(tmp_path)
    project_id = create_project(client)

    invalid = client.post(f"/api/projects/{project_id}/assets/model", files={"file": ("bad.txt", b"not image", "text/plain")})
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["error"]["code"] == "FILE_TYPE_NOT_SUPPORTED"

    job = client.post(f"/api/projects/{project_id}/jobs", json={"clothing_order": ["a", "b", "c"]})
    assert job.status_code == 400
    assert job.json()["detail"]["error"]["code"] == "MODEL_ASSET_REQUIRED"
