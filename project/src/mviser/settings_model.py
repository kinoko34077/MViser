"""Tk-free settings model (MViser#16): field catalogue, layered effective values,
comment-preserving edits of project / global YAML via ruamel.yaml."""

from __future__ import annotations

import copy
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from .global_settings import GLOBAL_SECTIONS, GlobalSettingsError, validate_global
from .lyric_layout import ALIGNS
from .motion import PRESETS
from .project_data import DEFAULTS, DISPLAY_MODES, ProjectError, normalize


@dataclass(frozen=True)
class Field:
    path: tuple[str, ...]
    label: str
    kind: str                       # str | int | float | bool | color | choice | size | position
    choices: tuple[str, ...] = ()
    tab: str = ""

    @property
    def key(self) -> str:
        return ".".join(self.path)

    @property
    def global_allowed(self) -> bool:
        allowed = GLOBAL_SECTIONS.get(self.path[0], ())
        return allowed is None or self.path[1] in allowed


FIELDS: tuple[Field, ...] = (
    Field(("project", "title"), "Title", "str", tab="Project"),
    Field(("project", "bpm"), "BPM", "float", tab="Project"),
    Field(("project", "key"), "Key (e.g. C, Am)", "str", tab="Project"),
    Field(("project", "fps"), "FPS", "int", tab="Project"),
    Field(("project", "resolution"), "Resolution (W x H)", "size", tab="Project"),
    Field(("project", "offset"), "Offset of 1:1 (s)", "float", tab="Project"),
    Field(("style", "background_color"), "Background", "color", tab="Style"),
    Field(("style", "text_color"), "Text colour", "color", tab="Style"),
    Field(("style", "chord_font_size"), "Chord font size", "int", tab="Style"),
    Field(("style", "font_path"), "Font file", "str", tab="Style"),
    Field(("style", "auto_chord_colors"), "Auto chord colours", "bool", tab="Style"),
    Field(("style", "lyric_font_size"), "Lyric font size", "int", tab="Lyrics"),
    Field(("style", "ruby_scale"), "Ruby scale", "float", tab="Lyrics"),
    Field(("style", "ruby_align"), "Ruby align", "choice", ALIGNS, tab="Lyrics"),
    Field(("style", "vertical"), "Vertical text", "bool", tab="Lyrics"),
    Field(("style", "lyric_position"), "Lyric position (x, y)", "position", tab="Lyrics"),
    Field(("motion", "enter"), "Enter motion", "choice", PRESETS, tab="Motion"),
    Field(("motion", "enter_duration"), "Enter duration (s)", "float", tab="Motion"),
    Field(("motion", "pulse"), "Beat pulse", "float", tab="Motion"),
    Field(("harmony", "notation"), "Chord notation", "choice", ("auto", "symbol", "degree", "tones", "pitch_set"),
          tab="Harmony"),
    Field(("harmony", "display"), "Chord label", "choice", DISPLAY_MODES, tab="Harmony"),
)
TABS = tuple(dict.fromkeys(f.tab for f in FIELDS))


class SettingsError(ValueError):
    pass


def _get(doc: Any, path: tuple[str, ...]) -> tuple[bool, Any]:
    cur = doc
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def parse_value(field: Field, text: str) -> Any:
    """GUI text -> typed value; raises SettingsError with the field key."""
    text = text.strip()
    try:
        if field.kind == "int":
            return int(text)
        if field.kind == "float":
            return float(text)
        if field.kind == "bool":
            if text.lower() in ("1", "true", "yes", "on"):
                return True
            if text.lower() in ("0", "false", "no", "off"):
                return False
            raise ValueError(text)
        if field.kind == "size":
            w, h = text.lower().replace("x", " ").replace(",", " ").split()
            return [int(w), int(h)]
        if field.kind == "position":
            if text == "":
                return None
            x, y = text.replace(",", " ").split()
            return [float(x), float(y)]
        if field.kind == "choice" and text not in field.choices:
            raise ValueError(f"choose one of {field.choices}")
        if field.kind in ("str", "color") and text == "":
            return None
        return text
    except ValueError as exc:
        raise SettingsError(f"{field.key}: invalid value {text!r} ({exc})") from exc


def format_value(field: Field, value: Any) -> str:
    if value is None:
        return ""
    if field.kind == "size":
        return f"{value[0]}x{value[1]}"
    if field.kind == "position":
        return f"{value[0]}, {value[1]}"
    if field.kind == "bool":
        return "true" if value else "false"
    return str(value)


class SettingsDocument:
    """One editable layer (project file or global file), comments preserved."""

    def __init__(self, path: Path, layer: str, global_doc: dict | None = None):
        if layer not in ("project", "global"):
            raise ValueError(layer)
        self.path, self.layer = Path(path), layer
        self.global_doc = global_doc or {}
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.indent(mapping=2, sequence=4, offset=2)
        if self.path.exists():
            self.data = self._yaml.load(self.path.read_text(encoding="utf-8")) or CommentedMap()
        else:
            self.data = CommentedMap()

    def fields(self) -> list[Field]:
        return [f for f in FIELDS if self.layer == "project" or f.global_allowed]

    def effective(self, field: Field) -> tuple[Any, str]:
        """(value, source) where source is 'project' | 'global' | 'builtin'."""
        layers = [("builtin", DEFAULTS), ("global", self.global_doc)]
        if self.layer == "project":
            layers.append(("project", self.data))
        else:
            layers[1] = ("global", self.data)
        value, source = None, "builtin"
        for name, doc in layers:
            found, v = _get(doc, field.path)
            if found:
                value, source = v, name
        return value, source

    def is_overridden(self, field: Field) -> bool:
        return _get(self.data, field.path)[0]

    def set(self, field: Field, value: Any) -> None:
        cur = self.data
        for part in field.path[:-1]:
            if part not in cur or not isinstance(cur[part], dict):
                cur[part] = CommentedMap()
            cur = cur[part]
        cur[field.path[-1]] = value

    def reset(self, field: Field) -> None:
        """Remove the override so the value is inherited again; prune empty sections."""
        found, _ = _get(self.data, field.path)
        if not found:
            return
        parent = self.data
        for part in field.path[:-1]:
            parent = parent[part]
        del parent[field.path[-1]]
        if not parent and len(field.path) > 1:
            del self.data[field.path[0]]

    def _plain(self) -> dict:
        return copy.deepcopy(YAML(typ="safe").load(self.dumps()) or {})

    def validate(self) -> None:
        plain = self._plain()
        try:
            if self.layer == "global":
                validate_global(plain)
                normalize({}, self.path.parent, None, plain)
            else:
                normalize(plain, self.path.parent, None, self.global_doc)
        except (ProjectError, GlobalSettingsError) as exc:
            raise SettingsError(str(exc)) from exc

    def dumps(self) -> str:
        buf = io.StringIO()
        self._yaml.dump(self.data, buf)
        return buf.getvalue()

    def save(self) -> None:
        self.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.dumps(), encoding="utf-8")
