"""Produce disposable Windows data to verify migration into the Linux container."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch


def main():
    root = Path(__file__).resolve().parents[1]
    result_root = root / "test-results" / "docker"
    runtime = result_root / "runtime-windows"
    os.environ["APP_DATA_DIR"] = str(result_root / "runtime-windows-import")
    os.environ["AGNES_API_KEY"] = ""
    # Imports occur after default app paths have been isolated.
    from fastapi.testclient import TestClient
    from backend.app.config import Settings
    from backend.app.main import create_app
    from backend.app.providers.mock import MockVideoProvider
    from backend.tests.test_workflow import prepare_project

    class FailingDownload(MockVideoProvider):
        def download_video(self, *args, **kwargs):
            raise RuntimeError("Synthetic migration interruption before output save")

    with TestClient(create_app(Settings(data_dir=runtime, agnes_api_key=""))) as client:
        project, clothing = prepare_project(client)
        first = client.post(f"/api/projects/{project}/jobs", json={"provider": "mock", "clothing_order": clothing})
        assert first.status_code == 201
        job_id = first.json()["data"]["id"]
        assert client.get(f"/api/jobs/{job_id}").json()["data"]["current_node"] == "finish_job"
        output = client.get(f"/api/jobs/{job_id}/outputs").json()["data"][0]
        video = client.get(output["video_url"]).content
        assert hashlib.sha256(video).hexdigest() == output["sha256"]
        with patch("backend.app.workflow.runner.MockVideoProvider", FailingDownload):
            failure = client.post(f"/api/projects/{project}/jobs", json={"provider": "mock", "clothing_order": clothing})
        assert failure.status_code == 201
        failed_id = failure.json()["data"]["id"]
        assert client.get(f"/api/jobs/{failed_id}").json()["data"]["error_code"] == "OUTPUT_GENERATION_FAILED"
        client.patch("/api/settings", json={"mode": "mock"})
        backup = client.post("/api/backups/export")
        assert backup.status_code == 201
        content = client.get(f"/api/backups/{backup.json()['data']['id']}/download").content
        (result_root / "windows-backup.zip").write_bytes(content)
        fixture = {"project": project, "job": job_id, "failed_job": failed_id,
                   "video_sha256": output["sha256"], "source_platform": "Windows",
                   "fixture_kind": "synthetic pixels, Mock Provider, no real Agnes key"}
        (result_root / "windows-backup-state.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        print(json.dumps(fixture, indent=2))


if __name__ == "__main__":
    main()
