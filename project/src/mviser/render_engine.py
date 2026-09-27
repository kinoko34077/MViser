"""SceneState -> RGB image (Pillow). Knows nothing about beats or events."""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .lyric_layout import layout_lyric
from .side_text import side_centres, tile_offsets
from .motion import MotionState
from .scene import SceneState

LAYERS = ("background", "chords", "lyrics")

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

    def _side_text(self, image: Image.Image, state: SceneState) -> None:
        cfg = self.style["side_text"]
        text = (state.side_text or "").strip()
        opacity = float(cfg["opacity"]) * state.lyric_motion.opacity
        if state.side == "none" or not text or opacity <= 0:
            return
        size = max(1, int(cfg["size"]))
        font = load_font(self.font_path, size)
        fill = _rgb(state.text_color) + (round(255 * min(opacity, 1.0)),)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        vertical = bool(cfg["vertical"])
        step = size * 1.05
        unit = len(text) * step if vertical else font.getlength(text)
        for cx in side_centres(state.side, self.width, float(cfg["margin"])):
            if vertical:
                for start in tile_offsets(self.height, unit, float(cfg["spacing"]), state.side_scroll):
                    for i, ch in enumerate(text):
                        draw.text((cx, start + i * step), ch, font=font, fill=fill, anchor="mt")
            else:  # horizontal text rotated along the strip is out of scope; lay runs top-to-bottom
                for start in tile_offsets(self.height, size * 1.2, float(cfg["spacing"]), state.side_scroll):
                    draw.text((cx, start), text, font=font, fill=fill, anchor="mt")
        image.alpha_composite(layer)

    def render_rgba(self, state: SceneState, layers: tuple[str, ...] = LAYERS) -> Image.Image:
        """Compose the selected layers (MViser#23). Without `background` the frame is transparent."""
        unknown = set(layers) - set(LAYERS)
        if unknown:
            raise ValueError(f"unknown layers {sorted(unknown)}; available: {LAYERS}")
        if "background" in layers:
            image = Image.new("RGBA", (self.width, self.height), _rgb(state.background_color) + (255,))
        else:
            image = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if "chords" in layers and state.chord_label:
            self._text(image, state.chord_label, (self.width / 2, self.height * 0.42),
                       int(self.style["chord_font_size"]), state.text_color, state.chord_motion, state.chord_scale)
        if "lyrics" in layers and state.lyric:
            self._side_text(image, state)
            self._lyric(image, state)
        return image

    def render(self, state: SceneState) -> Image.Image:
        return self.render_rgba(state).convert("RGB")
