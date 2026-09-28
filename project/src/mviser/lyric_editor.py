"""Tk-free lyric editing over the project YAML (MViser#25). Comments are preserved."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString
from ruamel.yaml.error import YAMLError

from .durable_io import atomic_write_text

from .project_data import ProjectError, compile_project, normalize
from .ruby import strip_ruby
from .timeline import BEATS_PER_MEASURE, Tempo


class LyricEditError(ValueError):
    pass


@dataclass(frozen=True)
class LyricRow:
    index: int
    at: Any
    text: str
    frame: int


def _yaml_at(value: Any) -> Any:
    # "M:B" must be quoted: YAML 1.1 readers (PyYAML) parse unquoted 4:4.5 as base-60 numbers.
    return DoubleQuotedScalarString(value) if isinstance(value, str) else value


def frame_to_position(tempo: Tempo, frame: int, mode: str = "tempo") -> Any:
    """Frame → `"M:B.bb"` (tempo-relative) or seconds, choosing the value that maps back to `frame`."""
    seconds = frame / tempo.fps
    if mode == "seconds" or seconds < tempo.offset:
        return round(seconds, 3)
    beats = (seconds - tempo.offset) / tempo.beat_sec
    measure = int(beats // BEATS_PER_MEASURE) + 1
    for digits in (2, 3, 4, 6):
        beat = round(beats - (measure - 1) * BEATS_PER_MEASURE + 1, digits)
        text = f"{measure}:{beat:g}"
        if tempo.seconds_to_frame(tempo.to_seconds(text)) == frame:
            return text
    return round(seconds, 6)


class LyricDocument:
    def __init__(self, path: Path | str, subtitle_set: str | None = None, global_doc: dict | None = None):
        self.path = Path(path)
        self.global_doc = global_doc or {}
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.indent(mapping=2, sequence=4, offset=2)
        try:
            self.data = self._yaml.load(self.path.read_text(encoding="utf-8")) or CommentedMap()
        except YAMLError as exc:
            raise LyricEditError(f"{self.path}: invalid YAML: {exc}") from exc
        compiled = self._compiled()
        available = compiled.doc["subtitle_sets"]
        if subtitle_set is not None and subtitle_set not in available and not (subtitle_set == "default"
                                                                             and not available):
            raise LyricEditError(f"unknown subtitle set {subtitle_set!r}; available: {available}")
        self.subtitle_set = subtitle_set or compiled.doc["active_subtitle_set"] or "default"
        self._undo: list[str] = []
        self._redo: list[str] = []

    # -- helpers --------------------------------------------------------------
    def _plain(self) -> dict:
        return YAML(typ="safe").load(self.dumps()) or {}

    def _compiled(self, subtitle_set: str | None = None):
        try:
            return compile_project(normalize(self._plain(), self.path.parent, subtitle_set, self.global_doc),
                                   self.path.parent)
        except ProjectError as exc:
            raise LyricEditError(str(exc)) from exc

    def _set_arg(self) -> str | None:
        """The set name to pass to the loader (None while the project has no lyrics yet)."""
        return self.subtitle_set if self.subtitle_set in self._compiled().doc["subtitle_sets"] else None

    @property
    def tempo(self) -> Tempo:
        return self._compiled().tempo

    def _list(self, create: bool = False) -> CommentedSeq | None:
        if self.subtitle_set == "default" and ("lyrics" in self.data or create and not self._named_sets()):
            if "lyrics" not in self.data:
                self.data["lyrics"] = CommentedSeq()
            return self.data["lyrics"]
        for item in self._named_sets():
            if item.get("name") == self.subtitle_set:
                if "lyrics" not in item:
                    item["lyrics"] = CommentedSeq()
                return item["lyrics"]
        if create:
            raise LyricEditError(f"subtitle set {self.subtitle_set!r} not found")
        return None

    def _named_sets(self) -> list:
        return list(self.data.get("subtitle_sets") or [])

    # -- queries --------------------------------------------------------------
    def rows(self) -> list[LyricRow]:
        seq = self._list() or []
        tempo = self.tempo
        out = []
        for i, item in enumerate(seq):
            text = item.get("text", item.get("value", ""))
            out.append(LyricRow(i, item.get("at"), str(text), tempo.seconds_to_frame(tempo.to_seconds(item["at"]))))
        return out

    # -- history (MViser#35) -------------------------------------------------------
    HISTORY_LIMIT = 100

    def _checkpoint(self) -> None:
        self._undo.append(self.dumps())
        del self._undo[:-self.HISTORY_LIMIT]
        self._redo.clear()

    def _restore(self, text: str) -> None:
        self.data = self._yaml.load(text) or CommentedMap()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.dumps())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.dumps())
        self._restore(self._redo.pop())
        return True

    # -- edits ----------------------------------------------------------------
    def add(self, frame: int, text: str, mode: str = "tempo") -> int:
        if not text.strip():
            raise LyricEditError("text must not be empty")
        self._checkpoint()
        seq = self._list(create=True)
        entry = CommentedMap()
        entry["at"] = _yaml_at(frame_to_position(self.tempo, frame, mode))
        entry["text"] = text
        seq.append(entry)
        return self.sort(keep=len(seq) - 1)

    def update(self, index: int, text: str | None = None, frame: int | None = None, mode: str = "tempo") -> int:
        seq = self._list(create=True)
        if not 0 <= index < len(seq):
            raise LyricEditError(f"no lyric at index {index}")
        if text is not None and not text.strip():
            raise LyricEditError("text must not be empty")
        self._checkpoint()
        item = seq[index]
        if text is not None:
            if not text.strip():
                raise LyricEditError("text must not be empty")
            item["text" if "text" in item or "value" not in item else "value"] = text
        if frame is not None:
            item["at"] = _yaml_at(frame_to_position(self.tempo, frame, mode))
        return self.sort(keep=index)

    def delete(self, index: int) -> None:
        seq = self._list(create=True)
        if not 0 <= index < len(seq):
            raise LyricEditError(f"no lyric at index {index}")
        self._checkpoint()
        del seq[index]

    def sort(self, keep: int | None = None) -> int:
        """Stable sort by frame; returns the new index of `keep`."""
        seq = self._list(create=True)
        tempo = self.tempo
        order = sorted(range(len(seq)), key=lambda i: (tempo.seconds_to_frame(tempo.to_seconds(seq[i]["at"])), i))
        if order != list(range(len(seq))):
            items = [seq[i] for i in order]
            seq.clear()
            seq.extend(items)
        return order.index(keep) if keep is not None else -1

    # -- persistence ----------------------------------------------------------
    def dumps(self) -> str:
        buf = io.StringIO()
        self._yaml.dump(self.data, buf)
        return buf.getvalue()

    def validate(self) -> None:
        self._compiled(self._set_arg())

    def save(self) -> None:
        self.validate()
        atomic_write_text(self.path, self.dumps())


def display_text(row: LyricRow) -> str:
    return strip_ruby(row.text)
