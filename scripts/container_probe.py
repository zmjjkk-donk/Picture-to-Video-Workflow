"""Run inside the Linux image; all media/database writes are disposable."""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import imageio.v2 as imageio
from PIL import Image
from sqlalchemy import create_engine, text
from imageio_ffmpeg import get_ffmpeg_exe


def main() -> None:
    assert sys.version_info[:2] == (3, 12), sys.version
    assert sys.executable == "/usr/local/bin/python", sys.executable
    assert os.getuid() == 10001, "Application must run as the non-root app user"
    assert shutil.which("node") is None and shutil.which("npm") is None
    assert not Path("/app/.env").exists()
    assert not Path("/app/.env.docker").exists()
    assert not Path("/app/data/text_picture").exists()
    assert Path("/app/frontend/dist/index.html").is_file()
    assert get_ffmpeg_exe() == "/usr/bin/ffmpeg"
    subprocess.run([get_ffmpeg_exe(), "-version"], check=True, capture_output=True)
    with tempfile.TemporaryDirectory(prefix="container-probe-") as directory:
        root = Path(directory)
        engine = create_engine(f"sqlite:///{(root / 'probe.db').as_posix()}")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE probe(value TEXT NOT NULL)"))
            connection.execute(text("INSERT INTO probe VALUES ('portable')"))
            assert connection.execute(text("SELECT value FROM probe")).scalar_one() == "portable"
        engine.dispose()
        video = root / "probe.mp4"
        writer = imageio.get_writer(video, fps=12, codec="libx264", macro_block_size=1)
        import numpy as np
        for colour in ("red", "green", "blue"):
            writer.append_data(np.asarray(Image.new("RGB", (32, 48), colour)))
        writer.close()
        reader = imageio.get_reader(video)
        assert reader.get_data(0).shape[:2] == (48, 32)
        assert 0 < reader.get_meta_data()["duration"] < 1
        reader.close()
    data = Path(os.environ["APP_DATA_DIR"])
    with tempfile.TemporaryDirectory(dir=data, prefix="write-probe-") as writable:
        (Path(writable) / "marker").write_text("writable", encoding="utf-8")
    print(json.dumps({"checks": 5, "result": "passed", "python": sys.version.split()[0],
                      "uid": os.getuid(), "ffmpeg": get_ffmpeg_exe(),
                      "packages": {p: importlib.metadata.version(p) for p in
                                   ("fastapi", "langgraph", "SQLAlchemy", "imageio-ffmpeg")}}, indent=2))


if __name__ == "__main__":
    main()
