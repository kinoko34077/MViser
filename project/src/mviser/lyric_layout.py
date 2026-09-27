"""Lyric layout with ruby and vertical text (MViser#6).

Pure geometry: glyph positions relative to the block centre (0, 0). The
renderer only draws the returned glyphs, so layout is testable without pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

ALIGNS = ("center", "left", "right")
RUBY_GAP = 0.15   # fraction of base size between base and ruby
LINE_STEP = 1.05  # vertical character advance, fraction of size

Measure = Callable[[str, int], float]  # (text, font_size) -> advance width


@dataclass(frozen=True)
class Glyph:
    text: str
    x: float          # left edge (horizontal) / centre (vertical)
    y: float          # top edge
    size: int
    ruby: bool = False
    width: float = 0.0

    @property
    def box(self) -> tuple[float, float, float, float]:
        if self.width:  # horizontal glyph run: x is left
            return (self.x, self.y, self.x + self.width, self.y + self.size)
        return (self.x - self.size / 2, self.y, self.x + self.size / 2, self.y + self.size)


def _center(glyphs: list[Glyph]) -> list[Glyph]:
    if not glyphs:
        return glyphs
    boxes = [g.box for g in glyphs]
    cx = (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2
    cy = (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2
    return [Glyph(g.text, g.x - cx, g.y - cy, g.size, g.ruby, g.width) for g in glyphs]


def _aligned(start: float, base_len: float, ruby_len: float, align: str) -> float:
    if align == "left":
        return start
    if align == "right":
        return start + base_len - ruby_len
    return start + (base_len - ruby_len) / 2


def layout_horizontal(segments, size: int, ruby_size: int, align: str, measure: Measure) -> list[Glyph]:
    glyphs: list[Glyph] = []
    x = 0.0
    ruby_y = -(ruby_size + size * RUBY_GAP)
    for base, ruby in segments:
        base_w = measure(base, size)
        ruby_w = measure(ruby, ruby_size) if ruby else 0.0
        advance = max(base_w, ruby_w)
        base_x = x + (advance - base_w) / 2
        glyphs.append(Glyph(base, base_x, 0.0, size, False, base_w))
        if ruby:
            glyphs.append(Glyph(ruby, _aligned(base_x, base_w, ruby_w, align), ruby_y, ruby_size, True, ruby_w))
        x += advance
    return _center(glyphs)


def layout_vertical(segments, size: int, ruby_size: int, align: str) -> list[Glyph]:
    glyphs: list[Glyph] = []
    y = 0.0
    step, ruby_step = size * LINE_STEP, ruby_size * LINE_STEP
    ruby_x = size / 2 + size * RUBY_GAP + ruby_size / 2
    for base, ruby in segments:
        base_len = len(base) * step
        ruby_len = len(ruby) * ruby_step if ruby else 0.0
        span = max(base_len, ruby_len)
        base_y = y + (span - base_len) / 2
        for i, ch in enumerate(base):
            glyphs.append(Glyph(ch, 0.0, base_y + i * step, size))
        if ruby:
            ry = _aligned(base_y, base_len, ruby_len, align)  # left=top, right=bottom
            for i, ch in enumerate(ruby):
                glyphs.append(Glyph(ch, ruby_x, ry + i * ruby_step, ruby_size, True))
        y += span
    return _center(glyphs)


def layout_lyric(segments, size: int, ruby_scale: float, align: str, vertical: bool,
                 measure: Measure) -> list[Glyph]:
    ruby_size = max(1, round(size * ruby_scale))
    if vertical:
        return layout_vertical(segments, size, ruby_size, align)
    return layout_horizontal(segments, size, ruby_size, align, measure)
