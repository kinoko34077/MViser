"""SceneState -> RGB image (Pillow). Knows nothing about beats or events."""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .lyric_layout import layout_lyric
from .motion import MotionState
from .scene import SceneState

# CJK-capable fonts first so lyrics render on every OS; Latin-only fonts last.
FONT_CANDIDATES = (
    "YuGothM.ttc", "C:/Windows/Fonts/YuGothM.ttc", "meiryo.ttc", "C:/Windows/Fonts/meiryo.ttc", "msgothic.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "NotoSansCJK-Regular.ttc", "NotoSansJP-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)
LATIN_FALLBACKS = ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "Arial.ttf")


@lru_cache(maxsize=1)
def _fontconfig_cjk() -> tuple[str, ...]:
    """Ask fontconfig (Linux/macOS with fc-match) for a Japanese-capable font."""
    exe = shutil.which("fc-match")
    if not exe:
        return ()
    try:
        out = subprocess.run([exe, "-f", "%{file}", "sans-serif:lang=ja"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ()
    return (out.stdout.strip(),) if out.returncode == 0 and out.stdout.strip() else ()


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


@lru_cache(maxsize=32)
def load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = ([font_path] if font_path else []) + list(FONT_CANDIDATES) + list(_fontconfig_cjk()) \
        + list(LATIN_FALLBACKS)
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


class Renderer:
    def __init__(self, resolution: tuple[int, int], style: dict, base_dir: Path | str = "."):
        self.width, self.height = resolution
        self.style = style
        font_path = style.get("font_path")
        self.font_path = str((Path(base_dir) / font_path).resolve()) if font_path else None

    def _text(self, image: Image.Image, text: str, center: tuple[float, float], size: int,
              color: str, motion: MotionState, scale: float = 1.0) -> None:
        if motion.opacity <= 0 or not text:
            return
        font = load_font(self.font_path, max(1, round(size * scale * motion.scale)))
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        cx = center[0] + motion.offset_x * self.width
        cy = center[1] + motion.offset_y * self.height
        alpha = round(255 * min(max(motion.opacity, 0.0), 1.0))
        draw.text((cx, cy), text, font=font, fill=_rgb(color) + (alpha,), anchor="mm")
        image.alpha_composite(layer)

    def _measure(self, text: str, size: int) -> float:
        return load_font(self.font_path, size).getlength(text)

    def _lyric(self, image: Image.Image, state: SceneState) -> None:
        motion = state.lyric_motion
        if motion.opacity <= 0:
            return
        size = int(self.style["lyric_font_size"])
        segments = state.lyric_segments or ((state.lyric, None),)
        glyphs = layout_lyric(segments, size, float(self.style["ruby_scale"]), state.lyric_align,
                              state.lyric_vertical, self._measure)
        cx = state.lyric_position[0] * self.width + motion.offset_x * self.width
        cy = state.lyric_position[1] * self.height + motion.offset_y * self.height
        alpha = round(255 * min(max(motion.opacity, 0.0), 1.0))
        fill = _rgb(state.text_color) + (alpha,)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for g in glyphs:
            font = load_font(self.font_path, g.size)
            # Baseline anchoring keeps separately drawn runs on one line regardless of their ink.
            ascent = font.getmetrics()[0] if hasattr(font, "getmetrics") else g.size
            anchor = "ls" if g.width else "ms"
            draw.text((cx + g.x, cy + g.y + ascent), g.text, font=font, fill=fill, anchor=anchor)
        image.alpha_composite(layer)

    def render(self, state: SceneState) -> Image.Image:
        image = Image.new("RGBA", (self.width, self.height), _rgb(state.background_color) + (255,))
        if state.chord_label:
            self._text(image, state.chord_label, (self.width / 2, self.height * 0.42),
                       int(self.style["chord_font_size"]), state.text_color, state.chord_motion, state.chord_scale)
        if state.lyric:
            self._lyric(image, state)
        return image.convert("RGB")
