"""Small persisted GUI state (MViser#20): recent project list."""

from __future__ import annotations

import json
from pathlib import Path

from .global_settings import global_path

RECENT_LIMIT = 10


def recent_path() -> Path:
    return global_path().parent / "recent.json"


def update_recent(recent: list[str], path: str | Path, limit: int = RECENT_LIMIT) -> list[str]:
    """Move `path` to the top, dedup (case-insensitive on Windows-style paths), cap."""
    entry = str(Path(path).resolve())
    key = entry.lower()
    rest = [p for p in recent if p.lower() != key]
    return [entry] + rest[: limit - 1]


def prune_missing(recent: list[str]) -> list[str]:
    return [p for p in recent if Path(p).exists()]


def load_recent(path: Path | None = None) -> list[str]:
    path = recent_path() if path is None else path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in data.get("recent", []) if isinstance(p, str)] if isinstance(data, dict) else []


def save_recent(recent: list[str], path: Path | None = None) -> None:
    path = recent_path() if path is None else path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"recent": recent}, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # recent files are a convenience; never block the GUI


# -- preferences (MViser#31) ------------------------------------------------------
PREF_DEFAULTS = {"theme": "light", "time_mode": "absolute", "guides": False, "chord_colors": True,
                 "side_panel": True, "side_width": 320}
PREF_CHOICES = {"theme": ("light", "dark"), "time_mode": ("absolute", "tempo", "frames")}


def prefs_path() -> Path:
    return global_path().parent / "gui_prefs.json"


def validate_prefs(data) -> dict:
    prefs = dict(PREF_DEFAULTS)
    if not isinstance(data, dict):
        return prefs
    for key, default in PREF_DEFAULTS.items():
        value = data.get(key, default)
        if key in PREF_CHOICES and value not in PREF_CHOICES[key]:
            continue
        if isinstance(default, bool) and not isinstance(value, bool):
            continue
        if isinstance(default, int) and not isinstance(default, bool) and (
                isinstance(value, bool) or not isinstance(value, int) or not 160 <= value <= 1200):
            continue
        prefs[key] = value
    return prefs


def load_prefs(path: Path | None = None) -> dict:
    path = prefs_path() if path is None else path
    try:
        return validate_prefs(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(PREF_DEFAULTS)


def save_prefs(prefs: dict, path: Path | None = None) -> None:
    path = prefs_path() if path is None else path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(validate_prefs(prefs), indent=2), encoding="utf-8")
    except OSError:
        pass
