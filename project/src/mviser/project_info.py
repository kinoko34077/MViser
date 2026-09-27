"""Help → Project info content (MViser#27), Tk-free."""

from __future__ import annotations

from pathlib import Path

from .global_settings import global_path
from .project_data import CompiledProject
from .time_format import format_time


def project_info(project: CompiledProject, path: Path | None = None) -> list[tuple[str, str]]:
    doc = project.doc
    p = doc["project"]
    width, height = project.resolution
    audio = project.audio_path
    rows = [
        ("File", str(path) if path else "-"),
        ("Title", str(p.get("title", ""))),
        ("BPM / key", f"{project.tempo.bpm:g} / {p.get('key') or '-'}"),
        ("FPS / resolution", f"{project.fps} / {width}x{height}"),
        ("Duration", f"{format_time(project.total_frames, project.tempo)}  "
                     f"({format_time(project.total_frames, project.tempo, 'tempo')}, {project.total_frames} frames)"),
        ("Chord events", str(len(project.tracks["chord"].events))),
        ("Lyric events", str(len(project.tracks["lyric"].events))),
        ("Subtitle sets", ", ".join(doc["subtitle_sets"]) or "-"),
        ("Active subtitle set", doc["active_subtitle_set"] or "-"),
        ("Audio", f"{audio} ({'found' if audio and audio.exists() else 'missing'})" if audio else "-"),
        ("Global settings", str(global_path())),
    ]
    return rows
