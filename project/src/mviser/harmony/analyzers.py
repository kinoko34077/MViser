"""ChordSpec -> analysis. Add a class + register it to add an analysis."""

from __future__ import annotations

from typing import Any, Protocol

from .model import ChordSpec, pitch_class_name
from .qualities import MINOR_LIKE, QUALITY_INTERVALS, QUALITY_SUFFIX

TOLERANCE_CENTS = 35.0  # JI 6:5 (+16c) and 7:4 (-31c) still read as their nearest 12-TET quality;
                        # quarter-tones (50c) do not. deviation_cents is always reported.


class ChordAnalyzer(Protocol):
    name: str

    def analyze(self, spec: ChordSpec, context: Any) -> ChordSpec: ...


class PitchClassAnalyzer:
    name = "pitch_classes"

    def analyze(self, spec: ChordSpec, context: Any) -> ChordSpec:
        cents = spec.absolute_cents()
        return spec.with_analysis(
            pitch_class_cents=[round(c, 3) for c in cents],
            pitch_classes=sorted({round(c / 100) % 12 for c in cents}),
            max_deviation_cents=round(max(abs(c / 100 - round(c / 100)) * 100 for c in cents), 3),
            microtonal=not spec.is_12tet,
        )


def _match(intervals: list[float], template: tuple[int, ...]) -> float | None:
    """Mean abs deviation if intervals equal template (as sets) within tolerance."""
    if len(intervals) != len(template):
        return None
    total = 0.0
    for got, want in zip(sorted(intervals), sorted(t * 100 for t in template)):
        dev = abs(got - want)
        if dev > TOLERANCE_CENTS:
            return None
        total += dev
    return total / len(template)


def identify(pitch_cents: list[float], bass_cents: float | None = None,
             root_hint: float | None = None) -> dict[str, Any]:
    """Pitch-class set -> best (root, quality) candidate, or UNKNOWN.

    Fail-open (MViser#2 MVP-1): never force a wrong chord; the raw set is
    returned alongside."""
    classes = sorted({round(c % 1200, 6) for c in pitch_cents})
    best: tuple[float, int, int, int, float, str] | None = None
    for root in classes:
        intervals = sorted((c - root) % 1200 for c in classes)
        for rank, (quality, template) in enumerate(QUALITY_INTERVALS.items()):
            dev = _match(intervals, template)
            if dev is None:
                continue
            bass_penalty = 0 if bass_cents is None or abs((bass_cents - root) % 1200) < TOLERANCE_CENTS else 1
            hint_penalty = 0 if root_hint is None or abs((root_hint - root) % 1200) < TOLERANCE_CENTS else 1
            key = (dev, hint_penalty, bass_penalty, rank, root, quality)
            if best is None or key < best:
                best = key
    if best is None:
        return {"quality": "UNKNOWN", "root_cents": None, "pitch_class_cents": classes}
    dev, _, _, _, root, quality = best
    symbol = pitch_class_name(round(root / 100) * 100) + QUALITY_SUFFIX[quality]
    if bass_cents is not None and abs((bass_cents - root) % 1200) >= TOLERANCE_CENTS:
        symbol += "/" + pitch_class_name(round(bass_cents / 100) * 100)
    return {"quality": quality, "root_cents": root, "symbol": symbol,
            "deviation_cents": round(dev, 3), "pitch_class_cents": classes}


class IdentifyAnalyzer:
    """Names chords whose mapper did not know the quality (tones / pitch sets)."""

    name = "identify"

    def analyze(self, spec: ChordSpec, context: Any) -> ChordSpec:
        result = identify(spec.absolute_cents(), spec.bass_cents, spec.root_cents)
        spec = spec.with_analysis(identified=result)
        if spec.quality is None and result["quality"] != "UNKNOWN":
            display = spec.display if spec.display not in ("?", "") else result["symbol"]
            spec = ChordSpec(display, result["root_cents"], tuple(
                t.__class__((spec.root_cents + t.cents - result["root_cents"]) % 1200, t.label, t.source)
                for t in spec.tones), result["quality"], spec.bass_cents, spec.source, spec.analysis)
        elif spec.display == "?":
            names = "-".join(pitch_class_name(c) for c in result["pitch_class_cents"])
            spec = ChordSpec(f"?({names})", spec.root_cents, spec.tones, spec.quality,
                             spec.bass_cents, spec.source, spec.analysis)
        return spec


_ROMAN_MAJOR = ("I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII")
_ROMAN_MINOR = ("I", "bII", "II", "III", "#III", "IV", "#IV", "V", "VI", "#VI", "VII", "#VII")
# degree -> accepted triad qualities (minor includes harmonic-minor V and vii°)
_DIATONIC_MAJOR = {0: {"major"}, 2: {"minor"}, 4: {"minor"}, 5: {"major"}, 7: {"major"}, 9: {"minor"}, 11: {"dim"}}
_DIATONIC_MINOR = {0: {"minor"}, 2: {"dim"}, 3: {"major"}, 5: {"minor"}, 7: {"minor", "major"},
                   8: {"major"}, 10: {"major"}, 11: {"dim"}}
_FUNCTION_MAJOR = {0: "tonic", 4: "tonic", 9: "tonic", 2: "subdominant", 5: "subdominant", 7: "dominant", 11: "dominant"}
_FUNCTION_MINOR = {0: "tonic", 3: "tonic", 2: "subdominant", 5: "subdominant", 8: "subdominant",
                   7: "dominant", 10: "dominant", 11: "dominant"}
_TRIAD_OF = {"7": "major", "maj7": "major", "6": "major", "add9": "major", "m7": "minor", "m6": "minor",
             "mmaj7": "minor", "m7b5": "dim", "dim7": "dim"}


class FunctionAnalyzer:
    """Roman numeral + coarse function relative to ``project.key`` (MViser#2 stage B, first cut)."""

    name = "function"

    def analyze(self, spec: ChordSpec, context: Any) -> ChordSpec:
        if context.key_cents is None:
            return spec
        quality = spec.quality or spec.analysis.get("identified", {}).get("quality")
        if quality in (None, "UNKNOWN"):
            return spec
        degree = round((spec.root_cents - context.key_cents) / 100) % 12
        minor = quality in MINOR_LIKE
        names = _ROMAN_MINOR if context.key_minor else _ROMAN_MAJOR
        numeral = names[degree].lower() if minor else names[degree]
        if quality in ("dim", "dim7"):
            numeral += "°"
        elif quality == "m7b5":
            numeral += "ø"
        diatonic_map = _DIATONIC_MINOR if context.key_minor else _DIATONIC_MAJOR
        functions = _FUNCTION_MINOR if context.key_minor else _FUNCTION_MAJOR
        diatonic = _TRIAD_OF.get(quality, quality) in diatonic_map.get(degree, set())
        return spec.with_analysis(
            approximate=not spec.is_12tet,
            roman=numeral,
            degree=degree,
            diatonic=diatonic,
            function=functions.get(degree, "other") if diatonic else "borrowed/chromatic",
        )
