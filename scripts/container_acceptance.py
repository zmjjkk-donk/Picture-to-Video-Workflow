"""Explicit Docker integration checks. Refuse to mutate ordinary application data.

Run with the designated host Python interpreter. Docker must be accessible.
Acceptance containers must carry matching labels and a disposable directory marker.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import time
import zipfile
from urllib.parse import urlsplit

import httpx
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = PROJECT_ROOT / "test-results" / "docker"


class Acceptance:
    def __init__(self, args):
        self.args = args
        self.passed: list[str] = []
        self.data = Path(args.data_dir).resolve()
        assert self.data.is_relative_to(RESULT_ROOT.resolve())
        assert self.data.name.startswith("runtime-"), "Only disposable acceptance directories are permitted"
        assert args.container.startswith("outfit-docker-check-")
        details = self.docker("inspect", args.container, json_result=True)[0]
        labels = details["Config"]["Labels"]
        assert labels["outfit-studio.purpose"] == "acceptance"
        assert (self.data / ".docker-acceptance").read_text().strip() == labels["outfit-studio.acceptance-id"]
        assert "AGNES_API_KEY=" in details["Config"]["Env"], "Do not run acceptance with a real model key"
        mounts = [m for m in details["Mounts"] if m["Destination"] == "/app/data"]
        assert len(mounts) == 1 and mounts[0]["Type"] == "bind"
        source = mounts[0]["Source"].replace("\\", "/").lower()
        expected = self.data.as_posix().lower()
        # Docker Desktop may report its Linux translation of a Windows bind path.
        if source.startswith("/run/desktop/mnt/host/"):
            source = source.removeprefix("/run/desktop/mnt/host/")
            expected = expected.replace(":/", "/", 1)
        assert source == expected, (source, expected)
        binding = details["HostConfig"]["PortBindings"]["8000/tcp"][0]
        assert binding["HostIp"] == "127.0.0.1"
        assert urlsplit(args.base_url).hostname == "127.0.0.1"
        assert int(binding["HostPort"]) == urlsplit(args.base_url).port
        self.client = httpx.Client(base_url=args.base_url, timeout=30, trust_env=False)
        self.state_file = RESULT_ROOT / f"{args.container}-state.json"

    def docker(self, *arguments, json_result=False):
        result = subprocess.run([self.args.docker_exe, *arguments], capture_output=True,
                                text=True, encoding="utf-8", timeout=180)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout) if json_result else result.stdout

    def check(self, name, operation):
        operation()
        self.passed.append(name)
        print(f"PASS {name}", flush=True)

    def request(self, method, path, status=200, **kwargs):
        response = self.client.request(method, path, **kwargs)
        assert response.status_code == status, (method, path, response.status_code, response.text[:600])
        return response

    def api(self, method, path, status=200, **kwargs):
        body = self.request(method, path, status, **kwargs).json()
        assert body["success"] is True, body
        return body["data"]

    def wait_ready(self):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if self.client.get("/api/health").status_code == 200:
                    assert self.api("GET", "/api/system/info")["data_dir"] == "/app/data"
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        raise AssertionError("Container failed to become ready within 60 seconds")

    def static(self):
        self.wait_ready()
        self.check("healthy-api", lambda: self._healthy())
        home = self.request("GET", "/").text
        assert "AI Outfit Studio" in home
        self.check("same-origin-build-and-assets", lambda: self._assets(home))
        for path in ("/dashboard", "/projects", "/projects/new", "/projects/test-id", "/jobs/test-id",
                     "/assets", "/history", "/backups", "/settings"):
            self.check(f"refresh-{path}", lambda path=path: self._document(path, home))
        for path in ("/api/does-not-exist", "/assets/missing.js", "/assets/missing.css", "/.env", "/unrelated"):
            self.check(f"missing-{path}", lambda path=path: self._missing(path))
        self.check("head-and-method-boundary", lambda: self._methods())
        self.check("container-health-and-process-config", lambda: self._container_config())

    def _healthy(self):
        assert self.request("GET", "/api/health").json()["database"] == "ok"

    def _assets(self, home):
        paths = re.findall(r'(?:src|href)="([^\"]+\.(?:css|js))"', home)
        assert len(paths) >= 2
        for path in paths:
            response = self.request("GET", path)
            assert response.content
            if path.endswith(".js"):
                assert "http://127.0.0.1:8000/api" not in response.text
                assert '"/api"' in response.text
            if path.endswith(".css"):
                assert "--weather-" in response.text

    def _document(self, path, home):
        response = self.request("GET", path, headers={"Accept": "text/html"})
        assert response.text == home
        assert "text/html" in response.headers["content-type"]

    def _missing(self, path):
        assert "AI Outfit Studio" not in self.request("GET", path, status=404).text

    def _methods(self):
        assert self.request("HEAD", "/projects/new").content == b""
        self.request("POST", "/dashboard", status=405)

    def _container_config(self):
        details = self.docker("inspect", self.args.container, json_result=True)[0]
        assert details["Config"]["User"] == "app"
        command = details["Config"]["Cmd"]
        assert command[command.index("--workers") + 1] == "1"
        assert command[command.index("--host") + 1] == "0.0.0.0"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            details = self.docker("inspect", self.args.container, json_result=True)[0]
            if details["State"]["Health"]["Status"] == "healthy":
                return
            time.sleep(1)
        raise AssertionError("Docker HEALTHCHECK did not become healthy")

    def workflow(self):
        self.wait_ready()
        self.state = {}
        self.check("reject-invalid-upload", self._invalid_upload)
        self.check("create-save-four-images-and-order", self._prepare_workflow)
        self.check("generate-five-second-mock-video", self._generate)
        self.check("workflow-log-and-steps", self._logs)
        self.check("media-download-hashes-and-range", self._media)
        self.check("unknown-token-and-provider-config", self._providers)
        self.check("failed-agnes-job-and-same-id-resume", self._failed_resume)
        self.check("settings-save-and-secret-exclusion", self._settings)
        self.check("active-deletion-guards-and-cancellation", self._cancel)
        self.check("project-deletion-keeps-history-task-deletion-cleans-media", self._delete_history)
        self.save_state()

    def save_state(self):
        self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def load_state(self):
        self.state = json.loads(self.state_file.read_text(encoding="utf-8"))

    @staticmethod
    def picture(colour="blue"):
        stream = io.BytesIO()
        Image.new("RGB", (64, 96), colour).save(stream, format="PNG")
        return stream.getvalue()

    def prepare_project(self, name, duration=5):
        project = self.api("POST", "/api/projects", 201,
                           json={"name": name, "duration_seconds": duration})
        project_id = project["id"]
        model = self.api("POST", f"/api/projects/{project_id}/assets/model", 201,
                         files={"file": ("model.png", self.picture(), "image/png")})
        clothing = []
        for index, colour in enumerate(("red", "green", "yellow")):
            asset = self.api("POST", f"/api/projects/{project_id}/assets/clothing", 201,
                             data={"name": f"服装 {index + 1}", "slot_index": str(index)},
                             files={"file": (f"look-{index}.png", self.picture(colour), "image/png")})
            clothing.append(asset["id"])
        assets = self.api("GET", f"/api/projects/{project_id}/assets")
        assert len(assets) == 4
        assert self.api("GET", f"/api/projects/{project_id}")["asset_count"] == 4
        for asset in assets:
            assert asset["file_url"].startswith(self.args.base_url + "/api/")
            content = self.request("GET", asset["file_url"]).content
            assert hashlib.sha256(content).hexdigest() == asset["sha256"]
            Image.open(io.BytesIO(self.request("GET", asset["thumbnail_url"]).content)).verify()
        return project_id, clothing, model["id"]

    def _invalid_upload(self):
        project = self.api("POST", "/api/projects", 201, json={"name": "无效上传隔离测试"})
        response = self.request("POST", f"/api/projects/{project['id']}/assets/model", 400,
                                files={"file": ("bad.png", b"not-an-image", "image/png")})
        assert response.json()["detail"]["error"]
        assert not self.api("GET", f"/api/projects/{project['id']}/assets")
        self.api("DELETE", f"/api/projects/{project['id']}")

    def _prepare_workflow(self):
        project, clothing, model = self.prepare_project("Docker 工作流验收 · 五秒视频")
        order = clothing[::-1]
        self.api("POST", f"/api/projects/{project}/assets/reorder", json={"asset_ids": order})
        saved = self.api("GET", f"/api/projects/{project}/assets")
        assert [a["id"] for a in sorted((a for a in saved if a["asset_type"] == "clothing"),
                                      key=lambda a: a["slot_index"])] == order
        self.state.update(project=project, clothing=order, model=model)

    def wait_job(self, job_id, expected):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            job = self.api("GET", f"/api/jobs/{job_id}")
            if job["status"] in {"succeeded", "failed", "canceled"}:
                # Provider polling may report success before save_output finishes.
                # Accept a successful run only after the existing final node commits.
                if job["status"] == "succeeded" and job["current_node"] != "finish_job":
                    time.sleep(0.1)
                    continue
                assert job["status"] == expected, job
                return job
            time.sleep(0.1)
        raise AssertionError(f"Job {job_id} did not finish within 90 seconds")

    def _generate(self):
        job = self.api("POST", f"/api/projects/{self.state['project']}/jobs", 201,
                       json={"provider": "mock", "clothing_order": self.state["clothing"]})
        self.state["job"] = job["id"]
        result = self.wait_job(job["id"], "succeeded")
        assert result["progress"] == 100
        outputs = self.api("GET", f"/api/jobs/{job['id']}/outputs")
        assert len(outputs) == 1 and abs(outputs[0]["duration"] - 5) <= 0.15
        assert outputs[0]["width"] > 0 and outputs[0]["height"] > outputs[0]["width"]
        self.state["output"] = outputs[0]

    def _logs(self):
        logs = self.api("GET", f"/api/jobs/{self.state['job']}/logs")
        assert logs and any(log["node_name"] == "save_output" for log in logs)
        assert self.api("GET", f"/api/jobs/{self.state['job']}/steps") == []
        assert self.api("GET", f"/api/jobs/{self.state['job']}/artifacts") == []

    def _media(self):
        output = self.state["output"]
        video = self.request("GET", output["video_url"])
        assert hashlib.sha256(video.content).hexdigest() == output["sha256"]
        assert len(video.content) == output["file_size"]
        ranged = self.request("GET", output["video_url"], 206, headers={"Range": "bytes=0-31"})
        assert ranged.content == video.content[:32]
        assert ranged.headers["content-range"].startswith("bytes 0-31/")
        Image.open(io.BytesIO(self.request("GET", output["thumbnail_url"]).content)).verify()
        import imageio.v2 as imageio
        local = RESULT_ROOT / "mock-video.mp4"
        local.write_bytes(video.content)
        reader = imageio.get_reader(local)
        assert reader.get_data(0).shape[0] > reader.get_data(0).shape[1]
        assert abs(reader.get_meta_data()["duration"] - 5) <= 0.15
        reader.close()

    def _providers(self):
        job = self.api("GET", f"/api/jobs/{self.state['job']}")
        assert job["token_usage_status"] == "unavailable"
        providers = self.api("GET", "/api/providers")
        assert {p["name"] for p in providers} == {"mock", "agnes"}
        assert next(p for p in providers if p["name"] == "agnes")["configured"] is False
        assert self.api("POST", "/api/providers/agnes/validate")["configured"] is False

    def resume(self, job_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = self.client.post(f"/api/jobs/{job_id}/resume")
            if response.status_code == 200:
                assert response.json()["data"]["id"] == job_id
                return
            assert response.status_code == 409
            assert response.json()["detail"]["error"]["code"] == "JOB_STILL_STOPPING"
            time.sleep(0.1)
        raise AssertionError("Runner failed to release its execution guard")

    def _failed_resume(self):
        job = self.api("POST", f"/api/projects/{self.state['project']}/jobs", 201,
                       json={"provider": "agnes", "clothing_order": self.state["clothing"]})
        failed = self.wait_job(job["id"], "failed")
        assert failed["error_code"] == "KEY_NOT_CONFIGURED"
        self.resume(job["id"])
        assert self.wait_job(job["id"], "failed")["error_code"] == "KEY_NOT_CONFIGURED"
        self.state["failed_job"] = job["id"]

    def _settings(self):
        self.api("PATCH", "/api/settings", json={"mode": "mock", "api_key": "synthetic-secret-do-not-store"})
        settings = self.api("GET", "/api/settings")
        assert settings["mode"] == "mock" and "api_key" not in settings

    def _cancel(self):
        project, clothing, _ = self.prepare_project("Docker 取消保护验收", duration=60)
        job = self.api("POST", f"/api/projects/{project}/jobs", 201,
                       json={"provider": "mock", "clothing_order": clothing})
        self.request("DELETE", f"/api/jobs/{job['id']}", 409)
        self.request("DELETE", f"/api/projects/{project}", 409)
        assert self.api("POST", f"/api/jobs/{job['id']}/cancel")["status"] == "canceled"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            response = self.client.delete(f"/api/jobs/{job['id']}")
            if response.status_code == 200:
                break
            assert response.status_code == 409
            assert response.json()["detail"]["error"]["code"] == "JOB_STILL_STOPPING"
            assert self.api("GET", f"/api/jobs/{job['id']}")["status"] == "canceled"
            time.sleep(0.1)
        else:
            raise AssertionError("Canceled runner did not release its deletion guard")
        self.api("DELETE", f"/api/projects/{project}")

    def _delete_history(self):
        project, clothing, _ = self.prepare_project("Docker 删除关系验收")
        job = self.api("POST", f"/api/projects/{project}/jobs", 201,
                       json={"provider": "mock", "clothing_order": clothing})
        self.wait_job(job["id"], "succeeded")
        output = self.api("GET", f"/api/jobs/{job['id']}/outputs")[0]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            response = self.client.delete(f"/api/projects/{project}")
            if response.status_code == 200:
                assert response.json()["success"] is True
                break
            # The existing API protects final checkpoint cleanup as well.
            assert response.status_code == 409
            assert response.json()["detail"]["error"]["code"] == "PROJECT_HAS_ACTIVE_JOBS"
            assert self.api("GET", f"/api/jobs/{job['id']}")["current_node"] == "finish_job"
            time.sleep(0.1)
        else:
            raise AssertionError("Completed runner did not release its project deletion guard")
        self.request("GET", f"/api/projects/{project}", 404)
        assert all(p["id"] != project for p in self.api("GET", "/api/dashboard/recent-projects"))
        assert all(p["id"] != project for p in self.api("GET", "/api/projects"))
        assert self.api("GET", f"/api/jobs/{job['id']}")["project_deleted"] is True
        self.request("GET", output["video_url"])
        self.api("DELETE", f"/api/jobs/{job['id']}")
        self.request("GET", f"/api/jobs/{job['id']}", 404)
        self.request("GET", output["video_url"], 404)
        assert not (self.data / output["video_path"]).exists()

    def persistence(self):
        self.wait_ready()
        self.load_state()
        self.check("export-complete-zip-and-checksums", self._export)
        self.check("reject-invalid-zip", self._invalid_zip)
        self.check("delete-and-restore-snapshot", self._restore_export)
        self.check("import-and-restore-zip", self._restore_import)
        self.check("restart-preserves-records-and-media", self._restart)
        self.check("recreate-preserves-records-and-media", self._recreate)
        self.check("windows-backup-import-and-failed-job-resume", self._windows_migration)
        self.save_state()

    def _export(self):
        backup = self.api("POST", "/api/backups/export", 201)
        content = self.request("GET", f"/api/backups/{backup['id']}/download").content
        assert hashlib.sha256(content).hexdigest() == backup["sha256"]
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            assert {"app.db", "workflow_checkpoints.db", "manifest.json"}.issubset(names)
            assert not any(name.startswith("backups/") for name in names)
            manifest = json.loads(archive.read("manifest.json"))
            assert self.state["project"] in manifest["project_ids"]
            assert self.state["output"]["video_path"] in names
            for entry in manifest["files"]:
                content_bytes = archive.read(entry["path"])
                assert len(content_bytes) == entry["size"]
                assert hashlib.sha256(content_bytes).hexdigest() == entry["sha256"]
                assert b"synthetic-secret-do-not-store" not in content_bytes
        (RESULT_ROOT / "container-backup.zip").write_bytes(content)
        self.backup_bytes = content
        self.state["backup"] = backup["id"]
        self.save_state()

    def _invalid_zip(self):
        response = self.request("POST", "/api/backups/import", 400,
                                files={"file": ("invalid.zip", b"bad-zip", "application/zip")})
        assert response.json()["detail"]["error"]["code"] == "BACKUP_INVALID"

    def verify_saved(self):
        project = self.api("GET", f"/api/projects/{self.state['project']}")
        assert project["asset_count"] == 4
        assert self.api("GET", f"/api/jobs/{self.state['job']}")["current_node"] == "finish_job"
        assert self.api("GET", f"/api/jobs/{self.state['failed_job']}")["error_code"] == "KEY_NOT_CONFIGURED"
        assert (self.data / "app.db").is_file()
        assert (self.data / "workflow_checkpoints.db").is_file()
        assert (self.data / self.state["output"]["video_path"]).is_file()
        content = self.request("GET", self.state["output"]["video_url"]).content
        assert hashlib.sha256(content).hexdigest() == self.state["output"]["sha256"]
        assert self.api("GET", "/api/settings")["mode"] == "mock"

    def _restore_export(self):
        self.api("DELETE", f"/api/projects/{self.state['project']}")
        self.request("GET", f"/api/projects/{self.state['project']}", 404)
        self.api("POST", f"/api/backups/{self.state['backup']}/restore", params={"mode": "replace"})
        self.verify_saved()

    def _restore_import(self):
        imported = self.api("POST", "/api/backups/import", 201,
                            files={"file": ("portable.zip", self.backup_bytes, "application/zip")})
        self.api("DELETE", f"/api/projects/{self.state['project']}")
        self.api("POST", f"/api/backups/{imported['id']}/restore", params={"mode": "replace"})
        self.verify_saved()

    def _restart(self):
        self.verify_saved()
        self.docker("stop", "--time", "150", self.args.container)
        details = self.docker("inspect", self.args.container, json_result=True)[0]
        assert details["State"]["ExitCode"] == 0
        self.docker("start", self.args.container)
        self.wait_ready()
        self.verify_saved()

    def _recreate(self):
        details = self.docker("inspect", self.args.container, json_result=True)[0]
        acceptance_id = details["Config"]["Labels"]["outfit-studio.acceptance-id"]
        self.docker("stop", "--time", "150", self.args.container)
        assert self.docker("inspect", self.args.container, json_result=True)[0]["State"]["ExitCode"] == 0
        self.docker("rm", self.args.container)
        self.docker("run", "-d", "--name", self.args.container,
                    "--label", "outfit-studio.purpose=acceptance",
                    "--label", f"outfit-studio.acceptance-id={acceptance_id}",
                    "--publish", f"127.0.0.1:{urlsplit(self.args.base_url).port}:8000",
                    "--env", "AGNES_API_KEY=", "--env", "APP_DATA_DIR=/app/data",
                    "--mount", f"type=bind,source={self.data},target=/app/data",
                    details["Config"]["Image"])
        self.wait_ready()
        self.verify_saved()

    def _windows_migration(self):
        fixture = json.loads((RESULT_ROOT / "windows-backup-state.json").read_text(encoding="utf-8"))
        content = (RESULT_ROOT / "windows-backup.zip").read_bytes()
        imported = self.api("POST", "/api/backups/import", 201,
                            files={"file": ("windows.zip", content, "application/zip")})
        self.api("POST", f"/api/backups/{imported['id']}/restore", params={"mode": "replace"})
        assert self.api("GET", f"/api/projects/{fixture['project']}")["asset_count"] == 4
        outputs = self.api("GET", f"/api/jobs/{fixture['job']}/outputs")
        assert len(outputs) == 1
        video = self.request("GET", outputs[0]["video_url"]).content
        assert hashlib.sha256(video).hexdigest() == fixture["video_sha256"]
        assert self.api("GET", f"/api/jobs/{fixture['failed_job']}")["error_code"] == "OUTPUT_GENERATION_FAILED"
        self.resume(fixture["failed_job"])
        self.wait_job(fixture["failed_job"], "succeeded")
        resumed = self.api("GET", f"/api/jobs/{fixture['failed_job']}/outputs")
        assert len(resumed) == 1 and abs(resumed[0]["duration"] - 5) <= 0.15
        assert resumed[0]["video_path"].startswith(f"projects/{fixture['project']}/")
        self.request("GET", resumed[0]["video_url"])
        self.state["windows_fixture"] = fixture
        # Return to our original snapshot so later checks use known fixture IDs.
        original = self.api("POST", "/api/backups/import", 201,
                            files={"file": ("container.zip", self.backup_bytes, "application/zip")})
        self.api("POST", f"/api/backups/{original['id']}/restore", params={"mode": "replace"})
        self.verify_saved()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-exe", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--phase", choices=["static", "workflow", "persistence", "all"], default="static")
    args = parser.parse_args()
    checks = Acceptance(args)
    try:
        if args.phase == "all":
            checks.static()
            checks.workflow()
            checks.persistence()
        else:
            getattr(checks, args.phase)()
        summary = {"phase": args.phase, "passed": len(checks.passed), "checks": checks.passed}
        (RESULT_ROOT / f"{args.phase}-result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    finally:
        checks.client.close()


if __name__ == "__main__":
    main()
