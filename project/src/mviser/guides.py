"""Preview guideline geometry (MViser#20). Overlay only; never rendered into exports."""

from __future__ import annotations

SAFE_AREAS = {"action": 0.9, "title": 0.8}


def guide_shapes(width: float, height: float, x0: float = 0.0, y0: float = 0.0) -> dict[str, list[tuple]]:
    """Lines (x1, y1, x2, y2) and rects (x1, y1, x2, y2) for an image placed at (x0, y0)."""
    cx, cy = x0 + width / 2, y0 + height / 2
    lines = [(cx, y0, cx, y0 + height), (x0, cy, x0 + width, cy)]  # centre cross
    thirds = []
    for k in (1, 2):
        thirds.append((x0 + width * k / 3, y0, x0 + width * k / 3, y0 + height))
        thirds.append((x0, y0 + height * k / 3, x0 + width, y0 + height * k / 3))
    rects = []
    for name, ratio in SAFE_AREAS.items():
        mx, my = width * (1 - ratio) / 2, height * (1 - ratio) / 2
        rects.append((x0 + mx, y0 + my, x0 + width - mx, y0 + height - my))
    return {"centre": lines, "thirds": thirds, "safe": rects}
