from __future__ import annotations

import subprocess
from pathlib import Path

import imageio.v2 as imageio
from PIL import Image
from imageio_ffmpeg import get_ffmpeg_exe


class MediaComposeError(RuntimeError):
    pass


def _duration(path: Path) -> float:
    try:
        reader = imageio.get_reader(path)
        meta = reader.get_meta_data()
        duration = float(meta.get("duration") or 0)
        reader.close()
        if duration > 0:
            return duration
    except Exception as exc:
        raise MediaComposeError(f"无法读取视频时长：{path}") from exc
    raise MediaComposeError(f"视频缺少有效时长：{path}")


def _make_cover(source: Path, target: Path) -> None:
    try:
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((720, 1280))
            canvas = Image.new("RGB", (720, 1280), (245, 245, 245))
            canvas.paste(image, ((720 - image.width) // 2, (1280 - image.height) // 2))
            target.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(target, format="PNG")
    except (OSError, ValueError) as exc:
        raise MediaComposeError(f"无法生成视频封面：{source}") from exc


def compose_segments(segment_paths: list[Path], output_path: Path, cover_source: Path, target_seconds: float = 5.0) -> tuple[int, int, float]:
    if len(segment_paths) != 2 or any(not path.is_file() for path in segment_paths):
        raise MediaComposeError("必须提供两段可用的过渡视频")
    if not cover_source.is_file():
        raise MediaComposeError("封面源图片不存在")
    durations = [_duration(path) for path in segment_paths]
    total = sum(durations)
    if total <= 0 or target_seconds <= 0:
        raise MediaComposeError("视频时长参数无效")
    factor = target_seconds / total
    filters = []
    for index in range(2):
        filters.append(f"[{index}:v]scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,setpts=PTS*{factor:.8f}[v{index}]")
    filters.append("[v0][v1]concat=n=2:v=1:a=0[outv]")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [get_ffmpeg_exe(), "-y"]
    for path in segment_paths:
        command.extend(["-i", str(path)])
    command.extend(["-filter_complex", ";".join(filters), "-map", "[outv]", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path)])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaComposeError(f"FFmpeg 合成失败：{exc}") from exc
    if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
        raise MediaComposeError(f"FFmpeg 合成失败：{result.stderr[-1000:]}")
    cover_path = output_path.with_name("cover.png")
    _make_cover(cover_source, cover_path)
    return 720, 1280, _duration(output_path)
