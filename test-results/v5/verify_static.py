"""Read-only verification of the production bundle served by the test server."""
import json
import re
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[2]
base = "http://127.0.0.1:8000"
with httpx.Client(timeout=20) as client:
    info = client.get(f"{base}/api/system/info")
    info.raise_for_status()
    assert Path(info.json()["data"]["data_dir"]).resolve() == (root / "test-results/v5/runtime").resolve()
    home = client.get(base)
    home.raise_for_status()
    paths = re.findall(r'(?:src|href)="([^\"]+\.(?:js|css))"', home.text)
    assert len(paths) == 2, paths
    files = []
    for path in paths:
        response = client.get(base + path)
        response.raise_for_status()
        assert len(response.content) > 100
        if path.endswith(".css"):
            assert "--weather-panel" in response.text
            assert "prefers-reduced-motion" in response.text
        else:
            assert "dashboard" in response.text
        files.append({"path": path, "status": response.status_code, "size": len(response.content)})
    health = client.get(f"{base}/api/health")
    health.raise_for_status()
    print(json.dumps({"home": home.status_code, "health": health.status_code, "resources": files}, ensure_ascii=False, indent=2))
