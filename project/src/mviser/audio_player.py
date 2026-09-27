"""Preview audio (MViser#12): FFmpeg decode + sounddevice output, audio-master clock.

The backend is injectable so start offset / clock / stop are testable without a
sound card. Any failure (no sounddevice, no PortAudio, no device) degrades to
silent playback; the GUI then falls back to its wall clock.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .video import find_ffmpeg

SAMPLE_RATE = 48000
CHANNELS = 2


def decode_pcm(path: Path, start: float = 0.0, rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> np.ndarray:
    """Whole file from `start` seconds as float32 array (frames, channels)."""
    cmd = [find_ffmpeg(), "-v", "error", "-ss", f"{max(start, 0.0):.6f}", "-i", str(path),
           "-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(channels), "-ar", str(rate), "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"audio decode failed: {proc.stderr.decode(errors='replace').strip()}")
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    return data[: len(data) // channels * channels].reshape(-1, channels)


class OutputBackend(Protocol):
    def start(self, pcm: np.ndarray, rate: int, offset: int) -> None: ...

    def stop(self) -> None: ...

    def position(self) -> int | None:  # samples played since offset, None when not playing
        ...


class SoundDeviceBackend:
    """Streams from an in-memory buffer via a PortAudio callback."""

    def __init__(self):
        import sounddevice  # noqa: F401  (raises ImportError / OSError when unavailable)

        self._sd = sounddevice
        self._stream = None
        self._played = 0

    def start(self, pcm: np.ndarray, rate: int, offset: int) -> None:
        self.stop()
        self._played = 0
        cursor = {"i": offset}

        def callback(outdata, frames, _time, _status):
            i = cursor["i"]
            chunk = pcm[i:i + frames]
            outdata[: len(chunk)] = chunk
            outdata[len(chunk):] = 0
            cursor["i"] = i + frames
            self._played += frames
            if len(chunk) < frames:
                raise self._sd.CallbackStop()

        self._stream = self._sd.OutputStream(samplerate=rate, channels=pcm.shape[1], dtype="float32",
                                             callback=callback)
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def position(self) -> int | None:
        if self._stream is None or not self._stream.active:
            return None
        latency = int(self._stream.latency * self._stream.samplerate) if self._stream.latency else 0
        return max(self._played - latency, 0)


def default_backend() -> tuple[OutputBackend | None, str | None]:
    try:
        return SoundDeviceBackend(), None
    except (ImportError, OSError) as exc:
        return None, f"audio output unavailable ({exc}); playing silently"


class AudioPlayer:
    def __init__(self, backend: OutputBackend | None = None, rate: int = SAMPLE_RATE, auto_backend: bool = True):
        if backend is None and auto_backend:
            backend, self.message = default_backend()
        else:
            self.message = None
        self.backend = backend
        self.rate = rate
        self.pcm: np.ndarray | None = None
        self.fps = 30
        self.muted = False
        self._start_frame = 0
        self._source: tuple[Any, ...] | None = None

    @property
    def available(self) -> bool:
        return self.backend is not None and self.pcm is not None and not self.muted

    def load(self, path: Path | None, start: float, fps: int) -> str | None:
        """(Re)decode when the source changes. Returns a user-facing message on failure."""
        self.fps = fps
        if path is None:
            self.pcm, self._source = None, None
            return None
        key = (str(path), path.stat().st_mtime if path.exists() else None, start)
        if key == self._source:
            return None
        try:
            self.pcm = decode_pcm(path, start, self.rate)
            self._source = key
        except (RuntimeError, OSError) as exc:
            self.pcm, self._source = None, None
            return str(exc)
        return None

    def sample_at_frame(self, frame: int) -> int:
        return int(round(frame / self.fps * self.rate))

    def play(self, frame: int) -> bool:
        """Start at `frame`. False when silent (caller uses its own clock)."""
        self.stop()
        if not self.available:
            return False
        offset = self.sample_at_frame(frame)
        if offset >= len(self.pcm):
            return False
        try:
            self.backend.start(self.pcm, self.rate, offset)
        except Exception as exc:  # device errors must not kill the GUI
            self.message = f"audio output failed ({exc}); playing silently"
            self.backend = None
            return False
        self._start_frame = frame
        return True

    def stop(self) -> None:
        if self.backend is not None:
            try:
                self.backend.stop()
            except Exception:
                pass

    def current_frame(self) -> int | None:
        """Frame from the audio clock, or None when audio is not driving playback."""
        if self.backend is None:
            return None
        played = self.backend.position()
        if played is None:
            return None
        return self._start_frame + int(played / self.rate * self.fps)
