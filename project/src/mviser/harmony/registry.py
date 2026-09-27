"""Mapper / analyzer registry: the single entry point for chord values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .analyzers import FunctionAnalyzer, IdentifyAnalyzer, PitchClassAnalyzer
from .mappers import DegreeMapper, MapperError, PitchSetMapper, SymbolMapper, TonesMapper
from .model import ChordSpec, PitchError, parse_pitch


class MappingError(ValueError):
    pass


@dataclass(frozen=True)
class HarmonyContext:
    key_cents: float | None = None
    key_minor: bool = False

    @classmethod
    def from_key(cls, key: str | None) -> "HarmonyContext":
        if not key:
            return cls()
        text = str(key).strip()
        minor = text.endswith("m") or text.lower().endswith("minor")
        tonic = text.split()[0].rstrip("m") if " " in text else text.rstrip("m")
        try:
            return cls(parse_pitch(tonic), minor)
        except PitchError as exc:
            raise MappingError(f"invalid key: {key!r}") from exc


class HarmonyRegistry:
    def __init__(self, mappers=(), analyzers=()):
        self.mappers = {m.name: m for m in mappers}
        self.analyzers = {a.name: a for a in analyzers}

    def register_mapper(self, mapper) -> None:
        self.mappers[mapper.name] = mapper

    def register_analyzer(self, analyzer) -> None:
        self.analyzers[analyzer.name] = analyzer

    def map(self, value: Any, context: HarmonyContext, notation: str | None = None) -> ChordSpec:
        if isinstance(value, dict) and "notation" in value:
            notation = value["notation"]
            value = value.get("value", {k: v for k, v in value.items() if k != "notation"})
        if notation and notation != "auto":
            mapper = self.mappers.get(notation)
            if mapper is None:
                raise MappingError(f"unknown notation {notation!r}; available: {sorted(self.mappers)}")
        else:
            mapper = next((m for m in self.mappers.values() if m.accepts(value)), None)
            if mapper is None:
                raise MappingError(f"no mapper accepts chord value {value!r}")
        try:
            return mapper.map(value, context)
        except (MapperError, PitchError, KeyError, TypeError) as exc:
            raise MappingError(f"{mapper.name}: {exc}") from exc

    def analyze(self, spec: ChordSpec, context: HarmonyContext, names=None) -> ChordSpec:
        for name in (names if names is not None else self.analyzers):
            analyzer = self.analyzers.get(name)
            if analyzer is None:
                raise MappingError(f"unknown analyzer {name!r}; available: {sorted(self.analyzers)}")
            spec = analyzer.analyze(spec, context)
        return spec

    def resolve(self, value: Any, context: HarmonyContext, notation: str | None = None, analyzers=None) -> ChordSpec:
        return self.analyze(self.map(value, context, notation), context, analyzers)


def default_registry() -> HarmonyRegistry:
    # Order matters for auto-detection: symbol before degree ("V" is not a note, "C" is).
    return HarmonyRegistry(
        mappers=[SymbolMapper(), DegreeMapper(), TonesMapper(), PitchSetMapper()],
        analyzers=[PitchClassAnalyzer(), IdentifyAnalyzer(), FunctionAnalyzer()],
    )
