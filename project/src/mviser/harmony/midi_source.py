"""Standard MIDI File source (MViser#2 MVP-1), built on ``mido``.

Notes become ``pitch_set`` chord events, so naming/UNKNOWN handling is done by
the ordinary mapper + identify analyzer path.

Modes:
- ``chords`` (default): one event per change of the sounding pitch set. Onsets
  closer than ``window`` seconds are merged (strummed / humanised chords). A held
  single note is a one-note set; silence ends the previous event.
- ``notes``: one event per note-on (melody / single notes); ends at note-off.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

DRUM_CHANNEL = 9


class MidiSourceError(ValueError):
    pass


def read_notes(path: Path, channels: list[int] | None = None, tracks: list[int] | None = None,
               exclude_drums: bool = True) -> list[tuple[float, float, int]]:
    """(start_sec, end_sec, midi_note) using the file's own tempo map."""
    try:
        import mido
    except ImportError as exc:  # pragma: no cover
        raise MidiSourceError("MIDI import needs 'mido' (pip install -r project/requirements.txt)") from exc
    try:
        midi = mido.MidiFile(str(path))
    except (OSError, EOFError, ValueError) as exc:
        raise MidiSourceError(f"{path}: cannot read MIDI: {exc}") from exc

    # Merge the selected tracks, keeping the tempo track so tick->second stays correct.
    selected = [t for i, t in enumerate(midi.tracks) if tracks is None or i in tracks
                or any(m.type == "set_tempo" for m in t)]
    ticks_per_beat = midi.ticks_per_beat
    tempo = 500000
    now = 0.0
    sounding: dict[tuple[int, int], list[float]] = {}
    notes: list[tuple[float, float, int]] = []
    for msg in mido.merge_tracks(selected):
        now += mido.tick2second(msg.time, ticks_per_beat, tempo)
        if msg.type == "set_tempo":
            tempo = msg.tempo
            continue
        if msg.type not in ("note_on", "note_off"):
            continue
        if exclude_drums and msg.channel == DRUM_CHANNEL:
            continue
        if channels is not None and msg.channel not in channels:
            continue
        key = (msg.channel, msg.note)
        if msg.type == "note_on" and msg.velocity > 0:
            sounding.setdefault(key, []).append(now)
        elif sounding.get(key):
            notes.append((sounding[key].pop(0), now, msg.note))
    for (_, note), starts in sounding.items():  # unterminated notes end at file end
        notes.extend((s, now, note) for s in starts)
    return sorted(notes)


def segment_chords(notes: list[tuple[float, float, int]], window: float = 0.05,
                   min_duration: float = 0.0) -> list[tuple[float, float, list[int]]]:
    """Pitch-set segments [(start, end, sorted_notes)] from overlapping notes."""
    if not notes:
        return []
    times = sorted({t for s, e, _ in notes for t in (s, e)})
    # Merge boundaries closer than `window` into the first one.
    merged: list[float] = []
    for t in times:
        if not merged or t - merged[-1] >= window:
            merged.append(t)
    snap = {t: max(m for m in merged if m <= t) for t in times}
    snapped = [(snap[s], snap[e], n) for s, e, n in notes if snap[e] > snap[s]]
    segments: list[tuple[float, float, list[int]]] = []
    for a, b in zip(merged, merged[1:]):
        active = sorted({n for s, e, n in snapped if s <= a < e})
        if not active:
            continue
        if segments and segments[-1][2] == active and abs(segments[-1][1] - a) < 1e-9:
            segments[-1] = (segments[-1][0], b, active)
        else:
            segments.append((a, b, active))
    return [seg for seg in segments if seg[1] - seg[0] >= min_duration]


def import_midi(path: Path, spec: dict[str, Any], start_seconds: float) -> list[dict[str, Any]]:
    mode = spec.get("mode", "chords")
    notes = read_notes(path, spec.get("channels"), spec.get("tracks"), spec.get("exclude_drums", True))
    if mode == "chords":
        segments = segment_chords(notes, float(spec.get("window", 0.05)), float(spec.get("min_duration", 0.0)))
    elif mode == "notes":
        segments = [(s, e, [n]) for s, e, n in notes]
    else:
        raise MidiSourceError(f"unknown MIDI mode {mode!r} (chords | notes)")
    return [{
        "type": "chord",
        "at": round(start_seconds + s, 6),
        "duration": round(e - s, 6),
        "notation": "pitch_set",
        "value": {"pitches": pitches},
    } for s, e, pitches in segments]
