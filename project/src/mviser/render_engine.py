"""SceneState -> RGB image (Pillow). Knows nothing about beats or events."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .motion import MotionState
from .scene import SceneState

FONT_CANDIDATES = (
    "NotoSansCJK-Regular.ttc",
    "NotoSansJP-Regular.ttf",
    "YuGothM.ttc",
    "meiryo.ttc",
    "msgothic.ttc",
    "DejaVuSans.ttf",
    "Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
)


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


@lru_cache(maxsize=32)
def load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = ([font_path] if font_path else []) + list(FONT_CANDIDATES)
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

    def render(self, state: SceneState) -> Image.Image:
        image = Image.new("RGBA", (self.width, self.height), _rgb(state.background_color) + (255,))
        if state.chord_label:
            self._text(image, state.chord_label, (self.width / 2, self.height * 0.42),
                       int(self.style["chord_font_size"]), state.text_color, state.chord_motion, state.chord_scale)
        if state.lyric:
            self._text(image, state.lyric, (self.width / 2, self.height * 0.82),
                       int(self.style["lyric_font_size"]), state.text_color, state.lyric_motion)
        return image.convert("RGB")
