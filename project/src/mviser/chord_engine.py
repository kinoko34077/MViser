"""Chord symbol parsing (MVP-0 stage A).

Harmonic-function analysis and audio/MIDI recognition are intentionally out of
scope here; see MViser#2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NOTE_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Longest suffixes first so that "maj7" wins over "m".
QUALITY_ALIASES = [
    ("maj7", "maj7"), ("M7", "maj7"), ("Δ7", "maj7"),
    ("m7b5", "m7b5"), ("ø", "m7b5"),
    ("dim7", "dim7"), ("dim", "dim"), ("°", "dim"),
    ("aug", "aug"), ("+", "aug"),
    ("sus2", "sus2"), ("sus4", "sus4"), ("sus", "sus4"),
    ("min7", "m7"), ("m7", "m7"), ("-7", "m7"),
    ("min", "minor"), ("m", "minor"), ("-", "minor"),
    ("7", "7"),
    ("6", "6"),
    ("maj", "major"),
]

_SYMBOL_RE = re.compile(r"^([A-G])([#♯b♭]*)(.*?)(?:/([A-G][#♯b♭]*))?$")
# What may follow a recognised quality: tensions like "9", "(b9,#11)", "add9", "omit5".
_EXTENSION_RE = re.compile(r"^(?:[\d#b♯♭(),\s]|add|omit|no)*$")


class ChordParseError(ValueError):
    pass


@dataclass(frozen=True)
class Chord:
    raw_symbol: str
    root: str
    root_pc: int
    quality: str
    extension: str = ""
    bass: str | None = None
    bass_pc: int | None = None

    @property
    def is_minor(self) -> bool:
        return self.quality in {"minor", "m7", "m7b5", "dim", "dim7"}


def _note(letter: str, accidentals: str) -> tuple[str, int]:
    acc = accidentals.replace("♯", "#").replace("♭", "b")
    pc = NOTE_PITCH[letter.upper()] + acc.count("#") - acc.count("b")
    return letter.upper() + acc, pc % 12


def parse_chord(symbol: str) -> Chord:
    """Parse symbols such as ``C``, ``Cm``, ``C#maj7``, ``Bb7``, ``Dm7/F``, ``Gsus4``.

    Unknown trailing text after a recognised quality is kept in ``extension``
    rather than rejected, so tensions are never silently lost.
    """
    raw = str(symbol).strip()
    match = _SYMBOL_RE.match(raw)
    if not match:
        raise ChordParseError(f"invalid chord symbol: {symbol!r}")
    letter, acc, rest, bass_text = match.groups()
    root, root_pc = _note(letter, acc)
    quality, extension = "major", rest
    for alias, name in QUALITY_ALIASES:
        if rest.startswith(alias):
            quality, extension = name, rest[len(alias):]
            break
    if not _EXTENSION_RE.match(extension):
        raise ChordParseError(f"unrecognised chord suffix {extension!r} in {symbol!r}")
    bass = bass_pc = None
    if bass_text:
        bass, bass_pc = _note(bass_text[0], bass_text[1:])
    return Chord(raw, root, root_pc, quality, extension.strip("()"), bass, bass_pc)
