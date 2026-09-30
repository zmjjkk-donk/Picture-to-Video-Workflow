from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw

from .base import ProviderStatus, VideoDownload, VideoJobRequest


class MockVideoProvider:
    """Local deterministic provider used until a real AI service is configured."""

    name = "mock"

    def __init__(self) -> None:
        self._jobs: dict[str, VideoJobRequest] = {}
        self._polls: dict[str, int] = {}

    def validate_config(self) -> None:
        return None

    def submit_video_job(self, request: VideoJobRequest) -> str:
        provider_job_id = f"mock-{uuid4()}"
        self._jobs[provider_job_id] = request
        self._polls[provider_job_id] = 0
        return provider_job_id

    def get_video_job_status(self, provider_job_id: str) -> ProviderStatus:
        if provider_job_id not in self._jobs:
            return ProviderStatus("failed", 0, "演示任务不存在")
        self._polls[provider_job_id] += 1
        if self._polls[provider_job_id] < 3:
            return ProviderStatus("processing", 45 + self._polls[provider_job_id] * 15, "演示 Provider 正在生成视频")
        return ProviderStatus("succeeded", 100, "演示视频已生成")

    def download_video(self, provider_job_id: str, output_dir: Path) -> VideoDownload:
        request = self._jobs[provider_job_id]
        output_dir.mkdir(parents=True, exist_ok=True)
        video_path = output_dir / "demo-outfit-change.mp4"
        thumbnail_path = output_dir / "demo-outfit-change.png"
        width, height, fps = 360, 640, 12
        frame_count = max(1, int(request.duration_seconds * fps))
        colors = [(226, 104, 116), (74, 135, 192), (58, 157, 111)]
        labels = ["LOOK 01", "LOOK 02", "LOOK 03"]
        writer = imageio.get_writer(video_path, format="mp4", fps=fps, codec="libx264", quality=7)
        first_frame: Image.Image | None = None
        try:
            for frame_index in range(frame_count):
                phase = frame_index / max(frame_count - 1, 1)
                look_index = min(2, int(phase * 3))
                local_phase = (phase * 3) % 1
                color = colors[look_index]
                image = Image.new("RGB", (width, height), (244, 240, 235))
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, width, 116), fill=(25, 29, 38))
                draw.text((24, 24), "AI OUTFIT STUDIO", fill=(255, 255, 255))
                draw.text((24, 70), "LOCAL MOCK PREVIEW", fill=(180, 190, 204))
                center_x = width // 2
                draw.ellipse((center_x - 45, 150, center_x + 45, 240), fill=(238, 198, 164), outline=(70, 70, 70))
                draw.rounded_rectangle((center_x - 85, 235, center_x + 85, 470), radius=35, fill=color, outline=(50, 50, 50), width=3)
                draw.polygon([(center_x - 85, 470), (center_x - 25, 470), (center_x - 35, 590), (center_x - 75, 590)], fill=(45, 48, 57))
                draw.polygon([(center_x + 25, 470), (center_x + 85, 470), (center_x + 75, 590), (center_x + 35, 590)], fill=(45, 48, 57))
                draw.text((24, 530), labels[look_index], fill=(25, 29, 38))
                draw.text((24, 565), "保持模特身份、背景和光线一致", fill=(78, 84, 94))
                bar_width = int((width - 48) * (local_phase if look_index < 2 else 1))
                draw.rounded_rectangle((24, 610, width - 24, 622), radius=6, fill=(210, 214, 220))
                draw.rounded_rectangle((24, 610, 24 + bar_width, 622), radius=6, fill=color)
                if first_frame is None:
                    first_frame = image.copy()
                writer.append_data(np.asarray(image))
        finally:
            writer.close()
        assert first_frame is not None
        first_frame.save(thumbnail_path, format="PNG")
        return VideoDownload(video_path=video_path, thumbnail_path=thumbnail_path, width=width, height=height, duration=float(request.duration_seconds))

    def cancel_video_job(self, provider_job_id: str) -> None:
        self._jobs.pop(provider_job_id, None)
        self._polls.pop(provider_job_id, None)
