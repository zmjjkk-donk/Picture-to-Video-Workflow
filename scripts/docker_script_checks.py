"""Exercise PowerShell deployment scripts, including an actual isolated start."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "test-results" / "docker"


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-exe", required=True)
    args = parser.parse_args()
    pwsh = shutil.which("pwsh")
    assert pwsh, "PowerShell 7 is required for this Windows script acceptance check"
    data = RESULTS / "runtime-script with spaces"
    dry_data = RESULTS / "runtime-script-dry-does-not-exist"
    config = RESULTS / "script-fixture.env"
    config.write_text("AGNES_API_KEY=\nAPP_DATA_DIR=/incorrect-path\n", encoding="utf-8")
    bad_config = RESULTS / "script-invalid.env"
    bad_config.write_text('AGNES_API_KEY="synthetic-placeholder"\n', encoding="utf-8")
    checks = []

    def command(script, parameters, dry=True, explicit=True):
        expression = "& " + quote(ROOT / "scripts" / script)
        if explicit:
            expression += " -DockerExe " + quote(args.docker_exe)
        for key, value in parameters.items():
            expression += f" -{key} " + quote(value)
        if dry:
            expression += " -DryRun | ConvertTo-Json -Depth 6"
        return subprocess.run([pwsh, "-NoProfile", "-Command", expression], cwd=ROOT.parent,
                              text=True, encoding="utf-8", capture_output=True, timeout=90)

    def passed(name):
        checks.append(name)
        print(f"PASS {name}", flush=True)

    build = command("docker-build.ps1", {})
    assert build.returncode == 0, build.stderr
    build_args = json.loads(build.stdout)["Arguments"]
    assert build_args[-1] == str(ROOT)
    assert "VITE_API_BASE=/api" in build_args
    passed("build-root-independent-of-current-directory")
    auto = command("docker-build.ps1", {}, explicit=False)
    assert auto.returncode == 0, auto.stderr
    assert Path(json.loads(auto.stdout)["Executable"]).is_file()
    passed("auto-find-installed-docker-without-explicit-path")
    run = command("docker-run.ps1", {"DataDir": dry_data, "EnvFile": config, "Port": "18001"})
    assert run.returncode == 0, run.stderr
    options = json.loads(run.stdout)
    assert options["DataDir"] == str(dry_data)
    assert not dry_data.exists(), "Dry run must not create any data directory"
    assert "127.0.0.1:18001:8000" in options["Arguments"]
    assert options["Arguments"][-2:] == ["APP_DATA_DIR=/app/data", "outfit-studio:docker-v1"]
    assert str(config) in options["Arguments"]
    assert "synthetic-placeholder" not in run.stdout
    passed("dry-run-port-bind-path-env-file-and-no-mutations")
    for name, parameters in (
        ("reject-quoted-env", {"EnvFile": bad_config}),
        ("reject-invalid-port", {"Port": "65536"}),
        ("reject-comma-mount-path", {"DataDir": "runtime,invalid"}),
        ("reject-missing-env-file", {"EnvFile": RESULTS / "not-present.env"}),
    ):
        rejected = command("docker-run.ps1", parameters)
        assert rejected.returncode != 0, name
        passed(name)
    name = "outfit-docker-check-script"
    # Never replace an existing container or delete its data to make a check pass.
    existing = subprocess.run([args.docker_exe, "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
                              capture_output=True, text=True, timeout=30)
    assert existing.returncode == 0 and not existing.stdout.strip(), "Acceptance container name is already in use"
    started = False
    try:
        started_result = command("docker-run.ps1", {"Name": name, "DataDir": data, "EnvFile": config, "Port": "18001"}, dry=False)
        assert started_result.returncode == 0, started_result.stderr
        started = True
        with httpx.Client(base_url="http://127.0.0.1:18001", trust_env=False, timeout=5) as client:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    if client.get("/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise AssertionError("Script-created container failed to become ready")
            assert client.get("/").status_code == 200
            assert client.get("/api/system/info").json()["data"]["data_dir"] == "/app/data"
            assert client.get("/api/projects").json()["data"] == []
        details = subprocess.run([args.docker_exe, "inspect", name], capture_output=True, text=True,
                                 encoding="utf-8", check=True, timeout=30)
        info = json.loads(details.stdout)[0]
        assert info["Config"]["Labels"]["outfit-studio.purpose"] == "application"
        assert info["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
        assert info["Config"]["StopTimeout"] == 150
        assert info["HostConfig"]["PortBindings"]["8000/tcp"][0]["HostIp"] == "127.0.0.1"
        assert "AGNES_API_KEY=" in info["Config"]["Env"]
        assert (data / "app.db").is_file()
        passed("actual-script-start-with-spaced-path-and-env-override")
    finally:
        if started:
            subprocess.run([args.docker_exe, "stop", "--time", "150", name], check=True, capture_output=True, timeout=180)
            subprocess.run([args.docker_exe, "rm", name], check=True, capture_output=True, timeout=30)
    summary = {"passed": len(checks), "checks": checks}
    (RESULTS / "script-result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
