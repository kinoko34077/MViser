"""Waveform peaks and beat grid for the timeline (MViser#18). Pure numpy / math."""

from __future__ import annotations

import numpy as np

from .timeline import BEATS_PER_MEASURE, Tempo


def waveform_peaks(pcm: np.ndarray, columns: int) -> np.ndarray:
    """(columns, 2) array of [min, max] in -1..1 over equal slices of the (mono-mixed) signal."""
    if columns <= 0:
        return np.zeros((0, 2), dtype=np.float32)
    mono = pcm.mean(axis=1) if pcm.ndim == 2 else pcm
    out = np.zeros((columns, 2), dtype=np.float32)
    if mono.size == 0:
        return out
    edges = np.linspace(0, mono.size, columns + 1).astype(int)
    for i in range(columns):
        chunk = mono[edges[i]:max(edges[i + 1], edges[i] + 1)]
        if chunk.size:
            out[i] = (chunk.min(), chunk.max())
    return np.clip(out, -1.0, 1.0)


def beat_grid(tempo: Tempo, total_frames: int, width: int) -> list[tuple[float, bool, int]]:
    """[(x, is_measure_start, measure_number)] for beats inside the timeline."""
    total_seconds = total_frames / tempo.fps
    if total_seconds <= 0 or width <= 0:
        return []
    lines = []
    beat = 0
    while True:
        t = tempo.offset + beat * tempo.beat_sec
        if t > total_seconds:
            break
        if t >= 0:
            measure = beat // BEATS_PER_MEASURE + 1
            lines.append((t / total_seconds * width, beat % BEATS_PER_MEASURE == 0, measure))
        beat += 1
    return lines
