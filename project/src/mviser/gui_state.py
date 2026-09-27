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
