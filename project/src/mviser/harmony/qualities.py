"""12-TET chord-quality templates shared by the symbol mapper and identifier."""

from __future__ import annotations

# quality -> semitones above root. Order = identification priority.
QUALITY_INTERVALS: dict[str, tuple[int, ...]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "m7b5": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "mmaj7": (0, 3, 7, 11),
    "7sus4": (0, 5, 7, 10),
    "add9": (0, 2, 4, 7),
}

QUALITY_SUFFIX: dict[str, str] = {
    "major": "", "minor": "m", "dim": "dim", "aug": "aug", "sus2": "sus2", "sus4": "sus4",
    "7": "7", "maj7": "maj7", "m7": "m7", "m7b5": "m7b5", "dim7": "dim7", "6": "6",
    "m6": "m6", "mmaj7": "mMaj7", "7sus4": "7sus4", "add9": "add9",
}

MINOR_LIKE = {"minor", "m7", "m7b5", "dim", "dim7", "m6", "mmaj7"}

# Extension degree -> semitones, for "C7(b9)" style tensions.
TENSION_SEMITONES = {"b9": 13, "9": 14, "#9": 15, "11": 17, "#11": 18, "b13": 20, "13": 21}
