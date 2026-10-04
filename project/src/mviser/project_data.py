"""`.mvproj.yaml` loading, validation, defaults and compilation to frames."""

from __future__ import annotations

import copy
import unicodedata
import wave
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

import yaml

from .durable_io import atomic_write_text

from .harmony import ChordSpec, HarmonyContext, MappingError, default_registry
from .harmony.sources import IMPORTERS, SourceError
from .motion import PRESETS
from .lyric_layout import ALIGNS
from .side_text import SIDE_DEFAULTS, SIDES, validate_side_text
from .ruby import parse_ruby, strip_ruby
from .styling import StyleRuleError, match_rules, validate_rules
from .timeline import BEATS_PER_MEASURE, Tempo, TimelineError, Track, build_track

SCHEMA_VERSION = 1
EVENT_TYPES = ("chord", "lyric")

DEFAULTS: dict[str, Any] = {
    "project": {
        "title": "Untitled",
        "key": None,
        "subtitle_set": None,
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
        "ruby_scale": 0.5,
        "ruby_align": "center",
        "vertical": False,
        "lyric_position": None,      # [x, y] fractions; default [0.5, 0.82] / vertical [0.88, 0.5]
        "side_text": {},             # MViser#19; see side_text.SIDE_DEFAULTS
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


def resolve_project_resource(base_dir: Path | str, value: Any, where: str) -> Path:
    """Resolve a project-declared file path and fail closed if it escapes the project directory."""
    if not isinstance(value, str) or not value.strip():
        raise ProjectError(f"{where}: path must be a non-empty relative string")

    win_path = PureWindowsPath(value)
    path = Path(value)
    if path.is_absolute() or win_path.is_absolute() or bool(win_path.drive):
        raise ProjectError(f"{where}: absolute/drive paths are not allowed")

    # Apply the same parent-traversal policy independent of the host OS/path separator.
    depth = 0
    for part in value.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if depth == 0:
                raise ProjectError(f"{where}: path escapes the project directory")
            depth -= 1
        else:
            depth += 1

    root = Path(base_dir).resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProjectError(f"{where}: path escapes the project directory") from exc
    return resolved


class _Loader(yaml.SafeLoader):
    """SafeLoader without YAML 1.1 base-60 numbers, so unquoted `at: 3:1` stays the string "3:1"."""


_Loader.yaml_implicit_resolvers = {
    key: [(tag, rx) for tag, rx in resolvers
          if not (tag in ("tag:yaml.org,2002:int", "tag:yaml.org,2002:float")
                  and (rx.match("3:1") or rx.match("4:4.5")))]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for _tag, _rx in (("tag:yaml.org,2002:int", r"^[-+]?(0b[0-1_]+|0[0-7_]+|(?:0|[1-9][0-9_]*)|0x[0-9a-fA-F_]+)$"),
                  ("tag:yaml.org,2002:float", r"^[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?$|^[-+]?\.[0-9_]+"
                                              r"(?:[eE][-+][0-9]+)?$|^[-+]?\.(?:inf|Inf|INF)$|^\.(?:nan|NaN|NAN)$")):
    import re as _re

    _Loader.add_implicit_resolver(_tag, _re.compile(_rx), list("-+0123456789."))


def yaml_load(text: str) -> Any:
    return yaml.load(text, Loader=_Loader)


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


FOLLOW = "follow"  # MViser#27: take the previous lyric event's value
FOLLOW_KEYS = {"ruby_align": "ruby_align", "vertical": "vertical", "position": "lyric_position"}  # event -> style


def _check_lyric_options(obj: dict[str, Any], where: str) -> None:
    if obj.get("ruby_align") is not None and obj["ruby_align"] not in ALIGNS + (FOLLOW,):
        raise ProjectError(f"{where}.ruby_align must be one of {ALIGNS + (FOLLOW,)}")
    if "vertical" in obj and not isinstance(obj["vertical"], bool) and obj["vertical"] != FOLLOW:
        raise ProjectError(f"{where}.vertical must be true, false or follow")
    for key in ("lyric_position", "position"):
        pos = obj.get(key)
        if pos is None or pos == FOLLOW:
            continue
        if (not isinstance(pos, (list, tuple)) or len(pos) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in pos)):
            raise ProjectError(f"{where}.{key} must be [x, y] fractions in 0..1")


SET_STYLE_KEYS = ("lyric_font_size", "ruby_scale", "ruby_align", "vertical", "lyric_position", "font_path", "text_color",
                  "side_text")


_WINDOWS_INVALID_LEAF_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_LEAFS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _validate_subtitle_set_name(value: Any, where: str) -> tuple[str, str]:
    """Return the original display name and a deterministic cross-platform output key."""
    if not isinstance(value, str) or not value:
        raise ProjectError(f"{where}.name must be a non-empty string")
    if value in {".", ".."} or value != value.rstrip(" ."):
        raise ProjectError(f"{where}.name must be a safe single filesystem leaf")
    if any(ord(ch) < 32 or ch in _WINDOWS_INVALID_LEAF_CHARS for ch in value):
        raise ProjectError(f"{where}.name must be a safe single filesystem leaf")
    win_path = PureWindowsPath(value)
    if win_path.drive or win_path.root:
        raise ProjectError(f"{where}.name must be a safe single filesystem leaf")
    if value.split(".", 1)[0].upper() in _WINDOWS_RESERVED_LEAFS:
        raise ProjectError(f"{where}.name must be a safe single filesystem leaf")
    output_key = unicodedata.normalize("NFC", value).casefold()
    return value, output_key


def _select_subtitle_set(doc: dict[str, Any], requested: str | None) -> None:
    """Fold the active subtitle set into `lyrics` + `style` (MViser#8)."""
    sets = list(doc.pop("subtitle_sets", None) or [])
    offset = 0
    if doc.get("lyrics"):
        sets.insert(0, {"name": "default", "lyrics": doc["lyrics"]})
        offset = 1
    names = []
    output_keys: dict[str, str] = {}
    for index, item in enumerate(sets):
        i = index - offset  # position in the user's `subtitle_sets` list
        if not isinstance(item, dict) or not isinstance(item.get("lyrics", []), list):
            raise ProjectError(f"subtitle_sets[{i}]: needs 'name' and a 'lyrics' list")
        name, output_key = _validate_subtitle_set_name(item.get("name"), f"subtitle_sets[{i}]")
        if name in names:
            raise ProjectError(f"subtitle_sets[{i}]: duplicate name {name!r}")
        previous = output_keys.get(output_key)
        if previous is not None:
            raise ProjectError(
                f"subtitle_sets[{i}].name: output name collision with {previous!r}"
            )
        names.append(name)
        output_keys[output_key] = name
        for key in item.get("style") or {}:
            if key not in SET_STYLE_KEYS:
                raise ProjectError(f"subtitle_sets[{i}].style.{key}: not a lyric setting (allowed: {SET_STYLE_KEYS})")
    wanted = requested or doc["project"].get("subtitle_set")
    if wanted is not None and wanted not in names:
        raise ProjectError(f"unknown subtitle set {wanted!r}; available: {names}")
    active = next((item for item in sets if item["name"] == wanted), sets[0] if sets else None)
    doc["subtitle_sets"] = names
    doc["active_subtitle_set"] = active["name"] if active else None
    doc["lyrics"] = list(active.get("lyrics") or []) if active else []
    if active and active.get("style"):
        doc["style"] = _merge(doc["style"], active["style"])


def normalize(raw: dict[str, Any], base_dir: Path | str = ".", subtitle_set: str | None = None,
              global_doc: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate a raw document and fill defaults. Returns a new dict."""
    if not isinstance(raw, dict):
        raise ProjectError("project file must be a mapping")
    version = raw.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ProjectError(f"unsupported schema_version: {version}")
    known = set(DEFAULTS) | {"schema_version", "events", "chords", "lyrics", "imports", "subtitle_sets"}
    unknown = set(raw) - known
    if unknown:
        raise ProjectError(f"unknown top-level keys: {sorted(unknown)}")
    base = {k: v for k, v in DEFAULTS.items() if v is not None}
    if global_doc:
        base = _merge(base, global_doc)  # built-in -> Global -> Project (MViser#16)
    doc = _merge(base, {k: v for k, v in raw.items() if v is not None})
    doc["schema_version"] = SCHEMA_VERSION

    # Project documents are not filesystem-authority grants. Validate every
    # project-declared font path, including inactive subtitle-set overrides,
    # before folding the active subtitle set into the effective style.
    raw_style = raw.get("style")
    if isinstance(raw_style, dict) and raw_style.get("font_path"):
        resolve_project_resource(base_dir, raw_style["font_path"], "style.font_path")
    for set_index, item in enumerate(raw.get("subtitle_sets") or []):
        if isinstance(item, dict):
            set_style = item.get("style")
            if isinstance(set_style, dict) and set_style.get("font_path"):
                resolve_project_resource(
                    base_dir,
                    set_style["font_path"],
                    f"subtitle_sets[{set_index}].style.font_path",
                )

    _select_subtitle_set(doc, subtitle_set)

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

    audio = doc.get("audio")
    if audio is not None:
        if not isinstance(audio, dict):
            raise ProjectError("audio must be a mapping")
        if audio.get("path"):
            resolve_project_resource(base_dir, audio["path"], "audio.path")

    style = doc["style"]
    style["background_color"] = _check_color(style["background_color"], "style.background_color")
    style["text_color"] = _check_color(style["text_color"], "style.text_color")
    for name, color in style["chord_colors"].items():
        style["chord_colors"][name] = _check_color(color, f"style.chord_colors.{name}")

    _check_lyric_options(style, "style")
    if not isinstance(style["side_text"], dict):
        raise ProjectError("style.side_text must be a mapping")
    errors = validate_side_text(style["side_text"], "style.side_text")
    if errors:
        raise ProjectError(errors[0])
    style["side_text"] = {**SIDE_DEFAULTS, **style["side_text"]}
    if not isinstance(style["ruby_scale"], (int, float)) or isinstance(style["ruby_scale"], bool) \
            or not 0 < style["ruby_scale"] <= 1:
        raise ProjectError("style.ruby_scale must be in (0, 1]")
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
            import_path = resolve_project_resource(base_dir, spec["path"], f"imports[{j}].path")
            imported = IMPORTERS[fmt](import_path, spec, start, tempo.beat_sec)
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
        if event["type"] == "lyric":
            _check_lyric_options(event, f"events[{i}]")
            if "repeat_side" in event and event["repeat_side"] not in SIDES:
                raise ProjectError(f"events[{i}].repeat_side must be one of {SIDES}")
            if "loop_text" in event and not isinstance(event["loop_text"], str):
                raise ProjectError(f"events[{i}].loop_text must be text")
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
        return resolve_project_resource(self.base_dir, audio["path"], "audio.path")

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
            payload["segments"] = tuple(parse_ruby(str(event["value"])))
            for key in ("ruby_align", "vertical", "position", "repeat_side", "loop_text"):
                if key in event:
                    payload[key] = event[key]
        starts[event["type"]].append((tempo.seconds_to_frame(seconds), payload))

    duration = project.get("duration")
    if duration is not None:
        seconds_total = tempo.to_seconds(duration)
    else:
        audio = doc.get("audio") or {}
        audio_len = wav_duration(resolve_project_resource(base_dir, audio["path"], "audio.path")) if audio.get("path") else None
        if audio_len is not None:
            seconds_total = max(audio_len - float(audio.get("start", 0.0)), 0.0)
        else:
            seconds_total = last_start + BEATS_PER_MEASURE * tempo.beat_sec
    total_frames = max(tempo.seconds_to_frame(seconds_total), 1)
    _resolve_follow(starts["lyric"], doc["style"])
    tracks = {t: build_track(t, s, total_frames) for t, s in starts.items()}
    return CompiledProject(doc, base_dir, tempo, total_frames, tracks, context)


def _resolve_follow(lyric_starts: list[tuple[int, dict[str, Any]]], style: dict[str, Any]) -> None:
    """Replace `follow` (explicit or via a style default) with the previous lyric's resolved value.
    The first lyric falls back to the built-in default."""
    previous: dict[str, Any] = {}
    for _frame, payload in sorted(lyric_starts, key=lambda item: item[0]):
        for key, style_key in FOLLOW_KEYS.items():
            value = payload.get(key, style.get(style_key))
            if value == FOLLOW:
                value = previous.get(key, DEFAULTS["style"][style_key])
            previous[key] = value
            if value is None:
                payload.pop(key, None)
            else:
                payload[key] = value


def load_project(path: Path | str, subtitle_set: str | None = None,
                 global_doc: dict[str, Any] | None = None) -> CompiledProject:
    path = Path(path)
    try:
        raw = yaml_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProjectError(f"{path}: invalid YAML: {exc}") from exc
    if global_doc is None:
        from .global_settings import GlobalSettingsError, load_global

        try:
            global_doc = load_global()
        except GlobalSettingsError as exc:
            raise ProjectError(f"global settings: {exc}") from exc
    return compile_project(normalize(raw or {}, path.parent, subtitle_set, global_doc), path.parent)


def save_project(doc: dict[str, Any], path: Path | str) -> None:
    text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
    atomic_write_text(path, text)


def chord_display(spec: ChordSpec, raw: Any, mode: str) -> str:
    if mode == "source" and isinstance(raw, str):
        return raw
    if mode == "roman" and "roman" in spec.analysis:
        return spec.analysis["roman"]
    return spec.display
