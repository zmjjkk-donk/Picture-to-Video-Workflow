from pathlib import Path
import re

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_local_frontend_dist_is_served_by_fastapi(tmp_path: Path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    home = client.get("/")
    assert home.status_code == 200
    assert "AI Outfit Studio" in home.text
    script_path = re.search(r'src="([^\"]+\.js)"', home.text)
    assert script_path is not None
    script = client.get(script_path.group(1))
    assert script.status_code == 200
    assert "dashboard" in script.text
