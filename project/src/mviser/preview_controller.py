"""Tk-free preview logic (MViser#10). The GUI view only forwards events here."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PIL import Image

from .project_data import CompiledProject, ProjectError, load_project
from .render_engine import Renderer
from .scene import chord_background, resolve_scene_state
from .timeline import BEATS_PER_MEASURE
from .waveform import beat_grid, waveform_peaks
from .video import FrameRange, write_frame_sequence, write_video


class PreviewController:
    def __init__(self, path: str | Path | None = None, subtitle_set: str | None = None):
        self.path: Path | None = None
        self.subtitle_set = subtitle_set
        self.project: CompiledProject | None = None
        self.renderer: Renderer | None = None
        self.frame = 0
        self.error: str | None = None
        self._mtime: float | None = None
        self._wave_pcm = None
        self._wave_key = None
        self._peaks_cache: dict[tuple, object] = {}
        if path is not None:
            self.load(path)

    # -- loading -----------------------------------------------------------
    def load(self, path: str | Path, subtitle_set: str | None = None) -> str | None:
        """Load a project; on failure keep the last good one and return the message."""
        path = Path(path)
        wanted = subtitle_set if subtitle_set is not None else self.subtitle_set
        try:
            project = load_project(path, wanted)
        except (ProjectError, OSError, ValueError) as exc:
            self.error = str(exc)
            return self.error
        self.path, self.project, self.subtitle_set = path, project, project.doc["active_subtitle_set"]
        self.renderer = Renderer(project.resolution, project.doc["style"], project.base_dir)
        self._mtime = self._stat(path)
        self.error = None
        self.seek(self.frame)
        return None

    @staticmethod
    def _stat(path: Path) -> float | None:
        try:
            return os.stat(path).st_mtime
        except OSError:
            return None

    def reload_if_changed(self) -> bool:
        if self.path is None:
            return False
        mtime = self._stat(self.path)
        if mtime is None or mtime == self._mtime:
            return False
        self._mtime = mtime  # do not retry a broken save on every poll
        self.load(self.path)
        return True

    def set_subtitle_set(self, name: str) -> str | None:
        return self.load(self.path, name) if self.path else None

    @property
    def subtitle_sets(self) -> list[str]:
        return list(self.project.doc["subtitle_sets"]) if self.project else []

    # -- navigation ----------------------------------------------------------
    @property
    def total_frames(self) -> int:
        return self.project.total_frames if self.project else 1

    @property
    def fps(self) -> int:
        return self.project.fps if self.project else 30

    def seek(self, frame: int) -> int:
        self.frame = max(0, min(int(frame), self.total_frames - 1))
        return self.frame

    def seek_seconds(self, seconds: float) -> int:
        return self.seek(round(seconds * self.fps))

    def step(self, frames: int) -> int:
        return self.seek(self.frame + frames)

    def _chord_starts(self) -> list[int]:
        return [e.start_frame for e in self.project.tracks["chord"].events] if self.project else []

    def next_chord(self) -> int:
        later = [s for s in self._chord_starts() if s > self.frame]
        return self.seek(later[0]) if later else self.frame

    def prev_chord(self) -> int:
        earlier = [s for s in self._chord_starts() if s < self.frame]
        return self.seek(earlier[-1]) if earlier else self.seek(0)

    # -- readout / rendering -------------------------------------------------
    def readout(self) -> dict[str, Any]:
        if not self.project:
            return {"time": "--:--.--", "position": "-", "chord": "", "roman": "", "lyric": "", "error": self.error}
        tempo = self.project.tempo
        t = self.frame / self.fps
        beats = tempo.beat_position(t)
        if beats >= 0:
            measure = int(beats // BEATS_PER_MEASURE) + 1
            position = f"{measure}:{beats - (measure - 1) * BEATS_PER_MEASURE + 1:.2f}"
        else:
            position = f"pre {beats:.2f}"
        state = resolve_scene_state(self.project, self.frame)
        chord = self.project.tracks["chord"].active(self.frame)
        roman = chord.payload["chord"].analysis.get("roman", "") if chord else ""
        return {
            "time": f"{int(t // 60):02d}:{t % 60:05.2f}",
            "frame": f"{self.frame}/{self.total_frames - 1}",
            "position": position,
            "chord": state.chord_label or "",
            "roman": roman,
            "lyric": state.lyric or "",
            "error": self.error,
        }

    def render(self, max_size: tuple[int, int] | None = None) -> Image.Image | None:
        if not self.project or not self.renderer:
            return None
        image = self.renderer.render(resolve_scene_state(self.project, self.frame))
        if max_size:
            w, h = image.size
            scale = min(max_size[0] / w, max_size[1] / h, 1.0)
            if scale < 1.0:
                image = image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)
        return image

    # -- timeline geometry ---------------------------------------------------
    def x_at_frame(self, frame: int, width: int) -> float:
        return frame / max(self.total_frames, 1) * width

    def frame_at_x(self, x: float, width: int) -> int:
        return self.seek(round(x / max(width, 1) * self.total_frames))

    def timeline_blocks(self, width: int) -> list[dict[str, Any]]:
        if not self.project:
            return []
        blocks = []
        for track in ("chord", "lyric"):
            for e in self.project.tracks[track].events:
                if e.end_frame <= e.start_frame:
                    continue
                p = e.payload
                blocks.append({
                    "track": track,
                    "x0": self.x_at_frame(e.start_frame, width),
                    "x1": self.x_at_frame(e.end_frame, width),
                    "label": p["display"] if track == "chord" else p["text"],
                    "color": chord_background(self.project, p) if track == "chord" else "#555555",
                    "start_frame": e.start_frame,
                })
        return blocks

    # -- waveform / grid (MViser#18) --------------------------------------------
    WAVE_RATE = 4000

    def _wave_source(self):
        project = self.project
        path = project.audio_path if project else None
        if path is None or not path.exists():
            return None
        key = (str(path), path.stat().st_mtime, project.audio_start)
        if key != self._wave_key:
            from .audio_player import decode_pcm

            try:
                self._wave_pcm = decode_pcm(path, project.audio_start, self.WAVE_RATE, 1)
            except (RuntimeError, OSError):
                self._wave_pcm = None
            self._wave_key, self._peaks_cache = key, {}
        return self._wave_pcm

    def waveform(self, width: int):
        """Peaks aligned to the timeline width (audio beyond the project end is cut), or None."""
        pcm = self._wave_source()
        if pcm is None or width <= 0:
            return None
        cache_key = (width, self.total_frames)
        if cache_key not in self._peaks_cache:
            samples = int(self.total_frames / self.fps * self.WAVE_RATE)
            clip = pcm[:samples]
            if len(clip) < samples:  # audio shorter than the project: pad with silence
                import numpy as np

                clip = np.concatenate([clip, np.zeros((samples - len(clip), clip.shape[1]), dtype=clip.dtype)])
            self._peaks_cache[cache_key] = waveform_peaks(clip, width)
        return self._peaks_cache[cache_key]

    def grid(self, width: int):
        return beat_grid(self.project.tempo, self.total_frames, width) if self.project else []

    # -- export --------------------------------------------------------------
    def export_video(self, out: str | Path, with_audio: bool = True, progress=None) -> Path:
        return write_video(self.project, out, FrameRange(0, self.total_frames), with_audio, progress)

    def export_frames(self, out_dir: str | Path, progress=None) -> list[Path]:
        return write_frame_sequence(self.project, out_dir, FrameRange(0, self.total_frames), progress)
