from pathlib import Path

from PIL import Image

from backend.app.providers.base import VideoJobRequest
from backend.app.providers.mock import MockVideoProvider
from backend.app.services.media import compose_segments


def test_compose_segments_keeps_two_inputs_and_normalizes_vertical_output(tmp_path: Path):
    provider = MockVideoProvider()
    source = tmp_path / "model.png"
    Image.new("RGB", (100, 160), (220, 120, 120)).save(source)
    segments = []
    for index in range(2):
        job_id = provider.submit_video_job(VideoJobRequest(job_id=str(index), prompt="demo", output_dir=tmp_path / f"segment-{index}", duration_seconds=1))
        result = provider.download_video(job_id, tmp_path / f"segment-{index}")
        segments.append(result.video_path)
    output = tmp_path / "final.mp4"
    width, height, duration = compose_segments(segments, output, source, target_seconds=5)
    assert output.is_file()
    assert output.read_bytes()[4:8] == b"ftyp"
    assert (tmp_path / "cover.png").is_file()
    assert (width, height) == (720, 1280)
    assert 4.5 <= duration <= 5.5
