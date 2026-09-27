"""External progression sources -> MViser chord events.

Each importer returns plain event dicts (``at`` in measure:beat, ``value`` in a
mapper notation), so imported data goes through the same Mapper/Analyzer path
as hand-written events.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..timeline import BEATS_PER_MEASURE


class SourceError(ValueError):
    pass


def _position(beat_index: float, start_beat: float) -> str:
    total = start_beat + beat_index
    measure = int(total // BEATS_PER_MEASURE) + 1
    beat = total - (measure - 1) * BEATS_PER_MEASURE + 1
    return f"{measure}:{beat:g}"


def import_mcb(path: Path, spec: dict[str, Any] | None = None, start_seconds: float = 0.0,
               beat_sec: float = 0.5) -> list[dict[str, Any]]:
    """μChordbot project (.mcb): progression parts -> tones-notation chord events.

    Pitch: root ``microStepInOctave`` / 100 = cents (μChordbot OCTAVE_MICROSTEP = 120000).
    Tones: ``localCent`` or the referenced PitchPreset ``cent``, plus ``octaveShift`` * 1200.
    """
    start_beat = start_seconds / beat_sec
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        payload = data["payload"]
    except (OSError, ValueError, KeyError) as exc:
        raise SourceError(f"{path}: not a μChordbot project: {exc}") from exc
    presets = {p["id"]: p for p in payload.get("pitchPresets", [])}
    chords = {c["id"]: c for c in payload.get("chordPresets", [])}
    events: list[dict[str, Any]] = []
    beat = 0.0
    for part in payload.get("progression", {}).get("parts", []):
        chord = chords.get(part.get("chordId"))
        if chord is None:
            raise SourceError(f"{path}: part {part.get('id')} references unknown chord {part.get('chordId')}")
        tones = []
        for tone in chord.get("tones", []):
            if tone.get("localCent") is not None:
                cents = float(tone["localCent"])
            elif tone.get("pitchPresetId") in presets:
                cents = float(presets[tone["pitchPresetId"]]["cent"])
            else:
                raise SourceError(f"{path}: chord {chord['id']} has an unresolved tone")
            cents += 1200 * int(tone.get("octaveShift", 0) or 0)
            tones.append({"cents": cents, "label": tone.get("label")})
        root = part.get("root", {})
        events.append({
            "type": "chord",
            "at": _position(beat, start_beat),
            "notation": "tones",
            "value": {
                "root": {"cents": float(root.get("microStepInOctave", 0)) / 100},
                "tones": tones,
                "name": None,
            },
            "label_hint": chord.get("name"),
        })
        beat += float(part.get("beats", BEATS_PER_MEASURE))
    return events


def _import_midi(path: Path, spec: dict[str, Any] | None = None, start_seconds: float = 0.0,
                 beat_sec: float = 0.5) -> list[dict[str, Any]]:
    from .midi_source import MidiSourceError, import_midi

    try:
        return import_midi(path, spec or {}, start_seconds)
    except MidiSourceError as exc:
        raise SourceError(str(exc)) from exc


# format -> importer(path, spec, start_seconds, beat_sec) -> event dicts
IMPORTERS: dict[str, Callable[..., list[dict[str, Any]]]] = {"mcb": import_mcb, "midi": _import_midi}
