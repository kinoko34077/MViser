"""Rendering checks: fonts / ruby geometry / side text — measured on real rendered frames."""

from __future__ import annotations

import numpy as np

from ..lyric_layout import layout_lyric
from ..project_data import load_project
from ..render_engine import Renderer, load_font
from ..scene import resolve_scene_state
from .core import FAIL, PASS, AuditContext, CheckResult, check

MISSING = "\U0010FFFD"  # private-use code point: renders as the font's .notdef glyph


def _glyph(font, ch: str) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("L", (96, 96))
    ImageDraw.Draw(img).text((8, 8), ch, font=font, fill=255)
    return img.tobytes()


def _alpha(image, box) -> int:
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    a = np.asarray(image.getchannel("A"))
    return int(a[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)].sum())


@check("jp-font", "Japanese glyphs and ruby geometry")
def jp_font(ctx: AuditContext) -> CheckResult:
    font = load_font(None, 64)
    path = getattr(font, "path", None)
    notdef = _glyph(font, MISSING)
    tofu = [ch for ch in "焦夢中こゆめなか" if _glyph(font, ch) == notdef]
    project = load_project(ctx.sample())
    renderer = Renderer(project.resolution, project.doc["style"], project.base_dir)
    geometry = {}
    for label, seconds in (("horizontal", 4.0), ("vertical", 9.5)):
        state = resolve_scene_state(project, project.tempo.seconds_to_frame(seconds))
        image = renderer.render_rgba(state, ("lyrics",))
        full = renderer.render(state)
        full.save(ctx.artifact(f"jp_font_{label}.png"))
        size = int(project.doc["style"]["lyric_font_size"])
        glyphs = layout_lyric(state.lyric_segments, size, float(project.doc["style"]["ruby_scale"]),
                              state.lyric_align, state.lyric_vertical, renderer._measure)
        cx, cy = state.lyric_position[0] * renderer.width, state.lyric_position[1] * renderer.height
        base = [g for g in glyphs if not g.ruby]
        ruby = [g for g in glyphs if g.ruby]
        shift = lambda b: (b[0] + cx, b[1] + cy, b[2] + cx, b[3] + cy)  # noqa: E731
        inked_ruby = all(_alpha(image, shift(g.box)) > 0 for g in ruby)
        inked_base = all(_alpha(image, shift(g.box)) > 0 for g in base)
        if label == "horizontal":
            placed = max(g.box[3] for g in ruby) <= min(g.box[1] for g in base) + 1
        else:
            placed = min(g.box[0] for g in ruby) >= max(g.box[2] for g in base) - 1
        geometry[label] = {"ruby_glyphs": len(ruby), "base_glyphs": len(base), "ruby_inked": inked_ruby,
                           "base_inked": inked_base, "ruby_placed": placed}
    ok = path and not tofu and all(all(v for k, v in g.items() if k.endswith(("inked", "placed")))
                                   for g in geometry.values())
    return CheckResult(
        "jp-font", PASS if ok else FAIL,
        f"font {path}; tofu {tofu or 'none'}; ruby above/right and inked" if ok else "Japanese rendering defect",
        values={"font_path": path, "tofu_chars": tofu, "geometry": geometry},
        rule="font resolved to a file; no sampled kana/kanji equals the .notdef glyph; every ruby/base glyph box "
             "contains ink; ruby box above base (horizontal) / right of base (vertical)",
        artifacts=[ctx.rel(ctx.artifact("jp_font_horizontal.png")), ctx.rel(ctx.artifact("jp_font_vertical.png"))])


@check("side-text", "Repeated side text fills both margins and scrolls")
def side_text(ctx: AuditContext) -> CheckResult:
    project = load_project(ctx.sample())
    renderer = Renderer(project.resolution, project.doc["style"], project.base_dir)
    w = renderer.width
    strips = []
    for i, seconds in enumerate((4.0, 4.5)):
        state = resolve_scene_state(project, project.tempo.seconds_to_frame(seconds))
        image = renderer.render_rgba(state, ("lyrics",))
        renderer.render(state).save(ctx.artifact(f"side_text_{i}.png"))
        a = np.asarray(image.getchannel("A"))
        strips.append((a[:, : int(w * 0.14)], a[:, int(w * 0.86):], state.side))
    (l0, r0, side), (l1, r1, _) = strips
    values = {"side": side, "left_ink": int(l0.sum() > 0), "right_ink": int(r0.sum() > 0),
              "scroll_changed_pixels": int((l0 != l1).sum() + (r0 != r1).sum())}
    ok = side == "both" and values["left_ink"] and values["right_ink"] and values["scroll_changed_pixels"] > 0
    return CheckResult("side-text", PASS if ok else FAIL,
                       "ink in both margins; strips move between t=4.0 s and 4.5 s" if ok else "side text missing",
                       values=values, rule="alpha > 0 in both 14 % margins; margin pixels differ 0.5 s later",
                       artifacts=[ctx.rel(ctx.artifact("side_text_0.png")), ctx.rel(ctx.artifact("side_text_1.png"))])
