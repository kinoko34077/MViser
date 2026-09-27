"""Rows for the docked chord list (MViser#33), Tk-free."""

from __future__ import annotations

from .project_data import CompiledProject
from .time_format import format_time


def chord_rows(project: CompiledProject, time_mode: str = "absolute") -> list[dict]:
    rows = []
    for e in project.tracks["chord"].events:
        if e.end_frame <= e.start_frame:
            continue
        a = e.payload["chord"].analysis
        rows.append({"frame": e.start_frame, "end": e.end_frame,
                     "time": format_time(e.start_frame, project.tempo, time_mode),
                     "display": e.payload["display"], "roman": a.get("roman", ""), "function": a.get("function", "")})
    return rows


def current_row(rows: list[dict], frame: int) -> int | None:
    for i, row in enumerate(rows):
        if row["frame"] <= frame < row["end"]:
            return i
    return None
