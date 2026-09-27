"""Decode helpers: frames and audio back from exported files (evidence from real outputs)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from ..video import find_ffmpeg


def probe(path: Path) -> str:
    return subprocess.run([find_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr


def decode_frames(path: Path, size: tuple[int, int], pix_fmt: str = "rgb24", limit: int | None = None) -> np.ndarray:
    """All frames as (n, h, w, c) uint8, scaled to `size`.
    VP9 alpha is only decoded by libvpx (FFmpeg's native vp9 decoder drops the alpha side stream)."""
    channels = 4 if pix_fmt == "rgba" else 3
    decoder = ["-c:v", "libvpx-vp9"] if Path(path).suffix.lower() == ".webm" else []
    cmd = [find_ffmpeg(), "-v", "error", *decoder, "-i", str(path), "-vf", f"scale={size[0]}:{size[1]}",
           "-f", "rawvideo", "-pix_fmt", pix_fmt]
    if limit:
        cmd += ["-frames:v", str(limit)]
    raw = subprocess.run(cmd + ["-"], capture_output=True, check=True).stdout
    frame = size[0] * size[1] * channels
    return np.frombuffer(raw[: len(raw) // frame * frame], dtype=np.uint8).reshape(-1, size[1], size[0], channels)


def decode_audio(path: Path, rate: int = 16000) -> np.ndarray:
    raw = subprocess.run([find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(rate),
                          "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def onsets(signal: np.ndarray, rate: int, threshold: float = 0.2, refractory: float = 0.1) -> list[float]:
    """Onset times (s) where the envelope crosses `threshold` × max, at most one per refractory window."""
    env = np.abs(signal)
    if env.size == 0 or env.max() <= 0:
        return []
    above = env > threshold * env.max()
    times, last = [], -1e9
    for idx in np.flatnonzero(above[1:] & ~above[:-1]) + 1:
        t = idx / rate
        if t - last >= refractory:
            times.append(t)
            last = t
    return times


def ink_bbox(image: Image.Image, background: tuple[int, int, int], tolerance: int = 40):
    """Bounding box of pixels differing from the background (None when blank)."""
    arr = np.asarray(image.convert("RGB")).astype(int)
    diff = np.abs(arr - np.array(background)).sum(axis=2) > tolerance
    if not diff.any():
        return None
    ys, xs = np.nonzero(diff)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
