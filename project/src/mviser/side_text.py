"""Repeated side text (MViser#19): pure tiling geometry for margin strips."""

from __future__ import annotations

SIDES = ("none", "left", "right", "both")
SIDE_DEFAULTS = {"side": "none", "size": 36, "spacing": 48, "opacity": 0.35, "margin": 0.06,
                 "scroll": 40.0, "vertical": True}


def tile_offsets(strip_length: float, unit_length: float, spacing: float, scroll_offset: float) -> list[float]:
    """Start positions (along the strip) of repeated units covering [0, strip_length).

    Units repeat every `unit_length + spacing`; `scroll_offset` shifts them forward
    with wrap-around, so any offset yields full coverage.
    """
    period = unit_length + max(spacing, 0.0)
    if strip_length <= 0 or period <= 0:
        return []
    shift = scroll_offset % period
    start = shift - period  # one tile before the strip so wrap-around is seamless
    offsets = []
    pos = start
    while pos < strip_length:
        if pos + unit_length > 0:
            offsets.append(pos)
        pos += period
    return offsets


def side_centres(side: str, width: int, margin: float) -> list[float]:
    """x centres of the strips for the chosen side(s)."""
    x = margin * width
    return {"none": [], "left": [x], "right": [width - x], "both": [x, width - x]}[side]


def validate_side_text(obj: dict, where: str) -> list[str]:
    """Return error messages (empty when valid)."""
    errors = []
    for key, value in obj.items():
        if key not in SIDE_DEFAULTS:
            errors.append(f"{where}.{key}: unknown key (allowed: {sorted(SIDE_DEFAULTS)})")
        elif key == "side" and value not in SIDES:
            errors.append(f"{where}.side must be one of {SIDES}")
        elif key == "vertical" and not isinstance(value, bool):
            errors.append(f"{where}.vertical must be true or false")
        elif key != "side" and key != "vertical" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            errors.append(f"{where}.{key} must be a number")
        elif key == "opacity" and not 0 <= value <= 1:
            errors.append(f"{where}.opacity must be in 0..1")
        elif key in ("size", "spacing") and value < 0:
            errors.append(f"{where}.{key} must be >= 0")
    return errors
