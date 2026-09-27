"""Frame iteration and FFmpeg output (adapter layer)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from PIL import Image

from .project_data import CompiledProject
from .render_engine import Renderer
from .scene import resolve_scene_state


class FFmpegNotFound(RuntimeError):
    pass


def find_ffmpeg() -> str:
    """MVISER_FFMPEG env > PATH > imageio-ffmpeg bundled binary."""
    explicit = os.environ.get("MVISER_FFMPEG")
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - environment dependent
        raise FFmpegNotFound("ffmpeg not found: install ffmpeg, set MVISER_FFMPEG, or pip install imageio-ffmpeg") from exc


@dataclass(frozen=True)
class FrameRange:
    start: int
    end: int  # exclusive

    @classmethod
    def from_seconds(cls, project: CompiledProject, start: float | None, end: float | None) -> "FrameRange":
        tempo = project.tempo
        s = tempo.seconds_to_frame(start) if start is not None else 0
        e = tempo.seconds_to_frame(end) if end is not None else project.total_frames
        s, e = max(0, s), min(project.total_frames, e)
        if e <= s:
            raise ValueError(f"empty frame range: {s}..{e}")
        return cls(s, e)


Progress = Callable[[int, int], None]


def iter_frames(project: CompiledProject, frame_range: FrameRange) -> Iterator[tuple[int, Image.Image]]:
    renderer = Renderer(project.resolution, project.doc["style"], project.base_dir)
    for frame in range(frame_range.start, frame_range.end):
        yield frame, renderer.render(resolve_scene_state(project, frame))


def write_frame_sequence(project: CompiledProject, out_dir: Path | str, frame_range: FrameRange,
                         progress: Progress | None = None) -> list[Path]:
    """PNG sequence named by absolute frame number (for AviUtl / After Effects)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i, (frame, image) in enumerate(iter_frames(project, frame_range)):
        path = out_dir / f"frame_{frame:06d}.png"
        image.save(path)
        written.append(path)
        if progress:
            progress(i + 1, frame_range.end - frame_range.start)
    return written


def write_video(project: CompiledProject, out_path: Path | str, frame_range: FrameRange,
                with_audio: bool = True, progress: Progress | None = None) -> Path:
    """Pipe raw RGB frames into FFmpeg and mux the (trimmed) audio."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = project.resolution
    fps = project.fps
    cmd = [find_ffmpeg(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-"]
    audio = project.audio_path if with_audio else None
    if audio is not None:
        if not audio.exists():
            raise FileNotFoundError(f"audio file not found: {audio}")
        seek = project.audio_start + frame_range.start / fps
        cmd += ["-ss", f"{seek:.6f}", "-i", str(audio)]
    duration = (frame_range.end - frame_range.start) / fps
    cmd += ["-map", "0:v:0"]
    if audio is not None:
        cmd += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", f"{duration:.6f}", str(out_path)]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    total = frame_range.end - frame_range.start
    try:
        assert proc.stdin is not None
        for i, (_, image) in enumerate(iter_frames(project, frame_range)):
            proc.stdin.write(image.tobytes())
            if progress:
                progress(i + 1, total)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    if proc.stderr:
        proc.stderr.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {stderr.strip()}")
    return out_path
