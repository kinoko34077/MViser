"""Notation-neutral chord representation.

Pitches are cents (float) so 12-TET, EDO, JI ratios and free cents share one
model — the same choice as μChordbot (microStep) and microtone-piano
(edo / cents / ratio pitch types).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

OCTAVE_CENTS = 1200.0
NOTE_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
_LETTER = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE_RE = re.compile(r"^([A-Ga-g])([#♯b♭]*)(-?\d+)?$")


class PitchError(ValueError):
    pass


@dataclass(frozen=True)
class Tone:
    cents: float                     # relative to the chord root
    label: str | None = None
    source: str | None = None        # e.g. "5:4", "edo31:10", "P5"


@dataclass(frozen=True)
class ChordSpec:
    """What every downstream consumer sees.

    ``root_cents``/``bass_cents`` are absolute pitch classes in [0, 1200) from C.
    ``quality`` is ``None`` when the mapper does not know it (Analyzers may
    fill it). ``source`` keeps the original notation so nothing is lost.
    """

    display: str
    root_cents: float
    tones: tuple[Tone, ...]
    quality: str | None = None
    bass_cents: float | None = None
    source: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)

    @property
    def root_name(self) -> str:
        return pitch_class_name(self.root_cents)

    @property
    def is_12tet(self) -> bool:
        cents = [self.root_cents] + [t.cents for t in self.tones]
        if self.bass_cents is not None:
            cents.append(self.bass_cents)
        return all(abs(c / 100 - round(c / 100)) < 1e-6 for c in cents)

    def absolute_cents(self) -> list[float]:
        return [(self.root_cents + t.cents) % OCTAVE_CENTS for t in self.tones]

    def with_analysis(self, **values: Any) -> "ChordSpec":
        merged = {**self.analysis, **values}
        return ChordSpec(self.display, self.root_cents, self.tones, self.quality,
                         self.bass_cents, self.source, merged)


def pitch_class_name(cents: float) -> str:
    semis = cents / 100
    nearest = round(semis)
    name = NOTE_NAMES[nearest % 12]
    dev = round((semis - nearest) * 100, 1)
    if abs(dev) < 0.05:
        return name
    return f"{name}{'+' if dev > 0 else ''}{dev:g}c"


def parse_pitch(value: Any) -> float:
    """Absolute pitch class in cents: ``"Eb"``, ``"A4"``, ``350`` (cents), ``{cents: 350}``."""
    if isinstance(value, bool):
        raise PitchError(f"invalid pitch: {value!r}")
    if isinstance(value, (int, float)):
        return float(value) % OCTAVE_CENTS
    if isinstance(value, dict):
        if "cents" in value:
            return float(value["cents"]) % OCTAVE_CENTS
        if "microStepInOctave" in value:  # μChordbot (.mcb) pitch
            return float(value["microStepInOctave"]) / 100 % OCTAVE_CENTS
        if "note" in value or "noteText" in value:
            return parse_pitch(value.get("note", value.get("noteText")))
    if isinstance(value, str):
        m = _NOTE_RE.match(value.strip())
        if m:
            acc = m.group(2).replace("♯", "#").replace("♭", "b")
            return float((_LETTER[m.group(1).upper()] + acc.count("#") - acc.count("b")) % 12 * 100)
    raise PitchError(f"invalid pitch: {value!r}")


_RATIO_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)\s*$")
_EDO_RE = re.compile(r"^\s*edo(\d+)\s*:\s*(-?\d+)\s*$", re.I)
_DEGREE = {"1": 0, "2": 200, "3": 400, "4": 500, "5": 700, "6": 900, "7": 1100}
_DEGREE_RE = re.compile(r"^([b#♭♯]*)(\d{1,2})$")


def parse_interval(value: Any) -> Tone:
    """Interval above the root: cents number, ``"5:4"``, ``"edo31:10"``, degree ``"b3"``/``"#11"``/``"P5"``."""
    if isinstance(value, dict):
        tone = parse_interval(value.get("cents", value.get("ratio", value.get("interval"))))
        return Tone(tone.cents, value.get("label", tone.label), tone.source)
    if isinstance(value, bool):
        raise PitchError(f"invalid interval: {value!r}")
    if isinstance(value, (int, float)):
        return Tone(float(value))
    text = str(value).strip()
    m = _RATIO_RE.match(text)
    if m:
        ratio = float(m.group(1)) / float(m.group(2))
        if ratio <= 0:
            raise PitchError(f"invalid ratio: {value!r}")
        return Tone(OCTAVE_CENTS * math.log2(ratio), source=text)
    m = _EDO_RE.match(text)
    if m:
        return Tone(OCTAVE_CENTS * int(m.group(2)) / int(m.group(1)), source=text)
    stripped = text[1:] if text[:1] in "PMmAd" and text[1:].isdigit() else text
    quality_prefix = text[:1] if stripped is not text else ""
    m = _DEGREE_RE.match(stripped)
    if m:
        number = int(m.group(2))
        base = _DEGREE.get(str((number - 1) % 7 + 1))
        if base is not None:
            acc = m.group(1).replace("♯", "#").replace("♭", "b")
            cents = base + 1200 * ((number - 1) // 7) + 100 * (acc.count("#") - acc.count("b"))
            cents += {"m": -100, "d": -100, "A": 100}.get(quality_prefix, 0)
            return Tone(float(cents), label=text, source=text)
    raise PitchError(f"invalid interval: {value!r}")
