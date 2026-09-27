"""User-level Global settings (MViser#16): built-in → Global → Project → Event."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

GLOBAL_SECTIONS: dict[str, tuple[str, ...] | None] = {
    "project": ("fps", "resolution"),  # per-song keys (title, bpm, key…) stay project-only
    "style": None,                     # None = every key of the section
    "motion": None,
    "harmony": None,
}


class GlobalSettingsError(ValueError):
    pass


def global_path(env: Mapping[str, str] | None = None, platform: str | None = None) -> Path:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if env.get("MVISER_GLOBAL"):
        return Path(env["MVISER_GLOBAL"])
    if platform.startswith("win"):
        base = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "MViser" / "global.yaml"
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MViser" / "global.yaml"
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "mviser" / "global.yaml"


def validate_global(doc: Any) -> dict[str, Any]:
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        raise GlobalSettingsError("global settings must be a mapping")
    for section, value in doc.items():
        if section not in GLOBAL_SECTIONS:
            raise GlobalSettingsError(f"global.{section}: not a global section (allowed: {sorted(GLOBAL_SECTIONS)})")
        if not isinstance(value, dict):
            raise GlobalSettingsError(f"global.{section} must be a mapping")
        allowed = GLOBAL_SECTIONS[section]
        for key in value:
            if allowed is not None and key not in allowed:
                raise GlobalSettingsError(f"global.{section}.{key}: project-only setting")
    return doc


def load_global(path: Path | None = None) -> dict[str, Any]:
    path = global_path() if path is None else path
    if not path.exists():
        return {}
    try:
        return validate_global(yaml.safe_load(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        raise GlobalSettingsError(f"{path}: invalid YAML: {exc}") from exc
