"""`.mvproj.yaml` loading, validation, defaults and compilation to frames."""

from __future__ import annotations

import copy
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .harmony import ChordSpec, HarmonyContext, MappingError, default_registry
from .harmony.sources import IMPORTERS, SourceError
from .motion import PRESETS
from .ruby import strip_ruby
from .styling import StyleRuleError, match_rules, validate_rules
from .timeline import BEATS_PER_MEASURE, Tempo, TimelineError, Track, build_track

SCHEMA_VERSION = 1
EVENT_TYPES = ("chord", "lyric")

DEFAULTS: dict[str, Any] = {
    "project": {
        "title": "Untitled",
        "key": None,
        "bpm": 120,
        "fps": 30,
        "resolution": [1920, 1080],
        "offset": 0.0,
        "duration": None,
    },
    "audio": None,
    "style": {
        "background_color": "#000000",
        "text_color": "#FFFFFF",
        "chord_font_size": 160,
        "lyric_font_size": 72,
        "font_path": None,
        "chord_colors": {},
        "auto_chord_colors": True,
        "rules": [],
    },
    "motion": {"enter": "fade", "enter_duration": 0.2, "pulse": 0.04},
    "harmony": {
        "notation": "auto",          # auto | symbol | degree | tones | pitch_set | <registered mapper>
        "analyzers": ["pitch_classes", "identify", "function"],
        "display": "symbol",         # symbol | source | roman
    },
}
DISPLAY_MODES = ("symbol", "source", "roman")


class ProjectError(ValueError):
    pass


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _check_color(value: Any, where: str) -> str:
    text = str(value)
    if not (text.startswith("#") and len(text) in (7, 9)):
        raise ProjectError(f"{where}: color must be #RRGGBB or #RRGGBBAA, got {value!r}")
    try:
        int(text[1:], 16)
    except ValueError as exc:
        raise ProjectError(f"{where}: invalid color {value!r}") from exc
    return text


def normalize(raw: dict[str, Any], base_dir: Path | str = ".") -> dict[str, Any]:
    """Validate a raw document and fill defaults. Returns a new dict."""
    if not isinstance(raw, dict):
        raise ProjectError("project file must be a mapping")
    version = raw.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ProjectError(f"unsupported schema_version: {version}")
    known = set(DEFAULTS) | {"schema_version", "events", "chords", "lyrics", "imports"}
    unknown = set(raw) - known
    if unknown:
        raise ProjectError(f"unknown top-level keys: {sorted(unknown)}")
    doc = _merge({k: v for k, v in DEFAULTS.items() if v is not None}, {k: v for k, v in raw.items() if v is not None})
    doc["schema_version"] = SCHEMA_VERSION

    project = doc["project"]
    try:
        width, height = (int(v) for v in project["resolution"])
    except (TypeError, ValueError) as exc:
        raise ProjectError("project.resolution must be [width, height]") from exc
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ProjectError("project.resolution must be positive even numbers (yuv420p)")
    project["resolution"] = [width, height]
    if not isinstance(project["fps"], int) or project["fps"] <= 0:
        raise ProjectError("project.fps must be a positive integer")

    style = doc["style"]
    style["background_color"] = _check_color(style["background_color"], "style.background_color")
    style["text_color"] = _check_color(style["text_color"], "style.text_color")
    for name, color in style["chord_colors"].items():
        style["chord_colors"][name] = _check_color(color, f"style.chord_colors.{name}")

    try:
        style["rules"] = validate_rules(style.get("rules"), _check_color)
    except StyleRuleError as exc:
        raise ProjectError(str(exc)) from exc
    if doc["harmony"]["display"] not in DISPLAY_MODES:
        raise ProjectError(f"harmony.display must be one of {DISPLAY_MODES}")
    motion = doc["motion"]
    if motion["enter"] not in PRESETS:
        raise ProjectError(f"motion.enter must be one of {PRESETS}")

    # Shorthand lists (as in MViser#2 examples) are folded into `events`.
    events = list(doc.get("events") or [])
    for item in doc.pop("chords", None) or []:
        events.append({"type": "chord", **{k: v for k, v in item.items() if k != "chord"}, "value": item.get("chord", item.get("value"))})
    for item in doc.pop("lyrics", None) or []:
        events.append({"type": "lyric", **{k: v for k, v in item.items() if k != "text"}, "value": item.get("text", item.get("value"))})
    for j, spec in enumerate(doc.get("imports") or []):
        fmt = spec.get("format") if isinstance(spec, dict) else None
        if fmt not in IMPORTERS or not spec.get("path"):
            raise ProjectError(f"imports[{j}]: needs format {sorted(IMPORTERS)} and path")
        try:
            tempo = Tempo(float(doc["project"]["bpm"]), int(doc["project"]["fps"]))
            start = tempo.to_seconds(spec.get("at", "1:1"))
            imported = IMPORTERS[fmt](Path(base_dir) / spec["path"], spec, start, tempo.beat_sec)
        except (SourceError, TimelineError) as exc:
            raise ProjectError(f"imports[{j}]: {exc}") from exc
        for event in imported:
            hint = event.pop("label_hint", None)
            if spec.get("use_names") and hint:
                event["value"]["name"] = hint
        events.extend(imported)
    for i, event in enumerate(events):
        if not isinstance(event, dict) or "at" not in event or event.get("value") in (None, ""):
            raise ProjectError(f"events[{i}]: requires 'at' and 'value'")
        if event.get("type") not in EVENT_TYPES:
            raise ProjectError(f"events[{i}]: type must be one of {EVENT_TYPES}")
        if "color" in event:
            event["color"] = _check_color(event["color"], f"events[{i}].color")
        if "notation" in event and event["type"] != "chord":
            raise ProjectError(f"events[{i}]: notation applies to chord events only")
        if event["type"] == "lyric" and not isinstance(event["value"], str):
            raise ProjectError(f"events[{i}]: lyric value must be text")
        if "motion" in event and event["motion"] not in PRESETS:
            raise ProjectError(f"events[{i}]: motion must be one of {PRESETS}")
        if "pulse" in event and (isinstance(event["pulse"], bool) or not isinstance(event["pulse"], (int, float))
                                 or event["pulse"] < 0):
            raise ProjectError(f"events[{i}]: pulse must be a non-negative number")
    doc["events"] = events
    return doc


@dataclass
class CompiledProject:
    doc: dict[str, Any]
    base_dir: Path
    tempo: Tempo
    total_frames: int
    tracks: dict[str, Track]
    harmony_context: HarmonyContext | None = None

    @property
    def fps(self) -> int:
        return self.tempo.fps

    @property
    def resolution(self) -> tuple[int, int]:
        width, height = self.doc["project"]["resolution"]
        return width, height

    @property
    def audio_path(self) -> Path | None:
        audio = self.doc.get("audio")
        if not audio or not audio.get("path"):
            return None
        return (self.base_dir / audio["path"]).resolve()

    @property
    def audio_start(self) -> float:
        audio = self.doc.get("audio") or {}
        return float(audio.get("start", 0.0))


def wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / float(handle.getframerate())
    except (wave.Error, EOFError, OSError):
        return None


def compile_project(doc: dict[str, Any], base_dir: Path | str = ".") -> CompiledProject:
    """Resolve every event to frames. Rendering only consumes this result."""
    base_dir = Path(base_dir)
    project = doc["project"]
    try:
        tempo = Tempo(float(project["bpm"]), int(project["fps"]), float(project["offset"]))
    except TimelineError as exc:
        raise ProjectError(str(exc)) from exc

    try:
        context = HarmonyContext.from_key(project.get("key"))
    except MappingError as exc:
        raise ProjectError(f"project.key: {exc}") from exc
    harmony = doc["harmony"]
    registry = default_registry()

    starts: dict[str, list[tuple[int, dict[str, Any]]]] = {t: [] for t in EVENT_TYPES}
    last_start = 0.0
    for i, event in enumerate(doc["events"]):
        try:
            seconds = tempo.to_seconds(event["at"])
        except (TimelineError, KeyError, TypeError, ValueError) as exc:
            raise ProjectError(f"events[{i}].at: {exc}") from exc
        last_start = max(last_start, seconds)
        payload: dict[str, Any] = {"value": event["value"], "seconds": seconds}
        for key in ("label", "color", "motion", "pulse"):
            if key in event:
                payload[key] = event[key]
        if "duration" in event:
            payload["duration_frames"] = tempo.seconds_to_frame(tempo.to_seconds(event["duration"]))
        if event["type"] == "chord":
            try:
                spec = registry.resolve(event["value"], context, event.get("notation", harmony["notation"]),
                                        harmony["analyzers"])
            except MappingError as exc:
                raise ProjectError(f"events[{i}]: {exc}") from exc
            payload["chord"] = spec
            payload["rule_style"] = match_rules(spec, doc["style"]["rules"])
            payload["display"] = chord_display(spec, event["value"], harmony["display"])
        else:
            payload["text"] = strip_ruby(str(event["value"]))
        starts[event["type"]].append((tempo.seconds_to_frame(seconds), payload))

    duration = project.get("duration")
    if duration is not None:
        seconds_total = tempo.to_seconds(duration)
    else:
        audio = doc.get("audio") or {}
        audio_len = wav_duration(base_dir / audio["path"]) if audio.get("path") else None
        if audio_len is not None:
            seconds_total = max(audio_len - float(audio.get("start", 0.0)), 0.0)
        else:
            seconds_total = last_start + BEATS_PER_MEASURE * tempo.beat_sec
    total_frames = max(tempo.seconds_to_frame(seconds_total), 1)
    tracks = {t: build_track(t, s, total_frames) for t, s in starts.items()}
    return CompiledProject(doc, base_dir, tempo, total_frames, tracks, context)


def load_project(path: Path | str) -> CompiledProject:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProjectError(f"{path}: invalid YAML: {exc}") from exc
    return compile_project(normalize(raw or {}, path.parent), path.parent)


def save_project(doc: dict[str, Any], path: Path | str) -> None:
    Path(path).write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def chord_display(spec: ChordSpec, raw: Any, mode: str) -> str:
    if mode == "source" and isinstance(raw, str):
        return raw
    if mode == "roman" and "roman" in spec.analysis:
        return spec.analysis["roman"]
    return spec.display
