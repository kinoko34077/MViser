"""Time display modes for the GUI (MViser#27)."""

from __future__ import annotations

from .timeline import BEATS_PER_MEASURE, Tempo

TIME_MODES = ("absolute", "tempo", "frames")


def format_time(frame: int, tempo: Tempo, mode: str = "absolute") -> str:
    if mode not in TIME_MODES:
        raise ValueError(f"time mode must be one of {TIME_MODES}")
    if mode == "frames":
        return f"f{frame}"
    seconds = frame / tempo.fps
    if mode == "absolute":
        return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"
    beats = tempo.beat_position(seconds)
    if beats < 0:
        return f"-{abs(beats):.2f}b"
    measure = int(beats // BEATS_PER_MEASURE) + 1
    return f"{measure}:{beats - (measure - 1) * BEATS_PER_MEASURE + 1:.2f}"
