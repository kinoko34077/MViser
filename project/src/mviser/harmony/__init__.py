"""Harmony layer: notation --(Mapper)--> ChordSpec --(Analyzer)--> analysis.

Everything downstream (timeline, scene, renderer) consumes only ``ChordSpec``.
New notations (MIDI, DSL, microtonal presets...) are added as Mappers; new
analyses (function, tension, voice leading...) as Analyzers. See
project/docs/adr/0002-harmony-mapper-layer.md.
"""

from .model import ChordSpec, Tone, parse_pitch, parse_interval
from .registry import HarmonyContext, HarmonyRegistry, MappingError, default_registry

__all__ = [
    "ChordSpec", "Tone", "parse_pitch", "parse_interval",
    "HarmonyContext", "HarmonyRegistry", "MappingError", "default_registry",
]
