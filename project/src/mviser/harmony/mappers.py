"""Notation -> ChordSpec mappers. Add a class + register it to support a new notation."""

from __future__ import annotations

import re
from typing import Any, Protocol

from ..chord_engine import ChordParseError, parse_chord
from .model import ChordSpec, PitchError, Tone, parse_interval, parse_pitch, pitch_class_name
from .qualities import QUALITY_INTERVALS, QUALITY_SUFFIX, TENSION_SEMITONES


class MapperError(ValueError):
    pass


class ChordMapper(Protocol):
    name: str

    def accepts(self, value: Any) -> bool: ...

    def map(self, value: Any, context: "Any") -> ChordSpec: ...


def _tones(semitones: tuple[int, ...]) -> tuple[Tone, ...]:
    return tuple(Tone(float(s * 100)) for s in semitones)


class SymbolMapper:
    """Chord symbols: ``C``, ``Dm7/F``, ``G7(b9)``."""

    name = "symbol"

    def accepts(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            parse_chord(value)
            return True
        except ChordParseError:
            return False

    def map(self, value: Any, context: Any) -> ChordSpec:
        try:
            chord = parse_chord(value)
        except ChordParseError as exc:
            raise MapperError(str(exc)) from exc
        semis = list(QUALITY_INTERVALS.get(chord.quality, (0, 4, 7)))
        for token in re.findall(r"[b#]?\d+", chord.extension):
            if token in TENSION_SEMITONES:
                semis.append(TENSION_SEMITONES[token])
        return ChordSpec(
            display=chord.raw_symbol,
            root_cents=float(chord.root_pc * 100),
            tones=_tones(tuple(dict.fromkeys(semis))),
            quality=chord.quality,
            bass_cents=float(chord.bass_pc * 100) if chord.bass_pc is not None else None,
            source={"notation": self.name, "raw": value, "extension": chord.extension},
        )


_ROMAN = {"I": 0, "II": 2, "III": 4, "IV": 5, "V": 7, "VI": 9, "VII": 11}
# In a minor key numerals follow natural minor (III = C in A minor), matching FunctionAnalyzer.
_ROMAN_MINOR = {"I": 0, "II": 2, "III": 3, "IV": 5, "V": 7, "VI": 8, "VII": 10}
_DEGREE_RE = re.compile(r"^([b#♭♯]?)(VII|VI|V|IV|III|II|I|vii|vi|v|iv|iii|ii|i)(°|ø|\+|[^/]*)?(?:/([b#]?)(VII|VI|V|IV|III|II|I|vii|vi|v|iv|iii|ii|i))?$")


class DegreeMapper:
    """Relative (key-dependent) progression: ``I``, ``vi``, ``V7``, ``bVII``, ``V/ii``.

    Case gives major/minor; suffix follows chord-symbol vocabulary. Requires
    ``project.key``; in minor keys numerals are relative to natural minor.
    """

    name = "degree"

    def accepts(self, value: Any) -> bool:
        return isinstance(value, str) and bool(_DEGREE_RE.match(value.strip()))

    def map(self, value: Any, context: Any) -> ChordSpec:
        m = _DEGREE_RE.match(str(value).strip())
        if not m:
            raise MapperError(f"invalid degree: {value!r}")
        if context.key_cents is None:
            raise MapperError(f"degree {value!r} needs project.key")
        acc, numeral, suffix, sec_acc, sec_numeral = m.groups()
        suffix = suffix or ""
        scale = _ROMAN_MINOR if context.key_minor else _ROMAN
        offset = scale[numeral.upper()] + {"b": -1, "♭": -1, "#": 1, "♯": 1}.get(acc, 0)
        if sec_numeral:  # secondary: V/ii = V of the ii degree
            offset += scale[sec_numeral.upper()] + {"b": -1, "#": 1}.get(sec_acc, 0)
        root = (context.key_cents + offset * 100) % 1200
        minor = numeral.islower()
        symbol_suffix = {"°": "dim", "ø": "m7b5", "+": "aug"}.get(suffix, suffix)
        if minor and not symbol_suffix.startswith(("m", "dim")):
            symbol_suffix = ("m" + symbol_suffix) if symbol_suffix not in ("7",) else "m7"
        spec = SymbolMapper().map(pitch_class_name(root) + symbol_suffix, context)
        return ChordSpec(spec.display, spec.root_cents, spec.tones, spec.quality, spec.bass_cents,
                         {"notation": self.name, "raw": value, "degree": value, "symbol": spec.display})


class TonesMapper:
    """Explicit / microtonal chords, μChordbot-style::

        {root: "A", tones: [0, "5:4", "3:2", "edo31:26"], bass: "E", name: "A just"}
    """

    name = "tones"

    def accepts(self, value: Any) -> bool:
        return isinstance(value, dict) and "tones" in value

    def map(self, value: Any, context: Any) -> ChordSpec:
        try:
            root = parse_pitch(value.get("root", 0))
            tones = tuple(parse_interval(t) for t in value["tones"])
            bass = parse_pitch(value["bass"]) if value.get("bass") is not None else None
        except (PitchError, TypeError) as exc:
            raise MapperError(str(exc)) from exc
        if not tones:
            raise MapperError("tones must not be empty")
        if all(abs(t.cents) > 1e-9 for t in tones):
            tones = (Tone(0.0, "R"),) + tones
        display = value.get("name") or "?"  # "?" lets the identify analyzer name it
        return ChordSpec(display, root, tones, value.get("quality"), bass,
                         {"notation": self.name, "raw": dict(value)})


class PitchSetMapper:
    """Absolute pitch set (future MIDI input path): ``{pitches: [57, 60, 64]}`` MIDI numbers
    or ``{pitch_classes: [9, 0, 4]}``. Root/quality are left to the identify analyzer."""

    name = "pitch_set"

    def accepts(self, value: Any) -> bool:
        return isinstance(value, dict) and ("pitches" in value or "pitch_classes" in value)

    def map(self, value: Any, context: Any) -> ChordSpec:
        if "pitches" in value:
            notes = sorted(float(p) for p in value["pitches"])
            bass = notes[0] * 100 % 1200 if notes else None
            classes = [n * 100 % 1200 for n in notes]
        else:
            classes = [float(p) * 100 % 1200 for p in value["pitch_classes"]]
            bass = None
        classes = list(dict.fromkeys(classes))
        if not classes:
            raise MapperError("empty pitch set")
        root = bass if bass is not None else classes[0]
        tones = tuple(Tone((c - root) % 1200) for c in classes)
        tones = tuple(sorted(tones, key=lambda t: t.cents))
        name = value.get("name") or (pitch_class_name(root) if len(classes) == 1 else "?")
        quality = "note" if len(classes) == 1 else None
        return ChordSpec(name, root, tones, quality, bass,
                         {"notation": self.name, "raw": dict(value)})
