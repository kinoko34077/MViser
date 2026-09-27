import unittest

import _path  # noqa: F401
from mviser.lyric_layout import layout_lyric
from mviser.project_data import ProjectError, compile_project, normalize
from mviser.render_engine import Renderer
from mviser.ruby import parse_ruby
from mviser.scene import resolve_scene_state


def mono(text, size):
    return len(text) * size


def by_text(glyphs):
    return {(g.text, g.ruby): g for g in glyphs}


class HorizontalTests(unittest.TestCase):
    def test_ruby_centred_above_base(self):
        glyphs = by_text(layout_lyric(parse_ruby("焦《こ》がれ"), 100, 0.5, "center", False, mono))
        base, ruby, rest = glyphs[("焦", False)], glyphs[("こ", True)], glyphs[("がれ", False)]
        self.assertAlmostEqual(ruby.x + ruby.width / 2, base.x + base.width / 2)
        self.assertLess(ruby.y + ruby.size, base.y)
        self.assertAlmostEqual(rest.x, base.x + base.width)  # no overlap with following text

    def test_long_ruby_widens_segment(self):
        glyphs = by_text(layout_lyric(parse_ruby("夢《ゆめみ》の"), 100, 0.5, "center", False, mono))
        base, ruby, rest = glyphs[("夢", False)], glyphs[("ゆめみ", True)], glyphs[("の", False)]
        self.assertGreaterEqual(rest.x, ruby.x + ruby.width - 1e-9)
        self.assertAlmostEqual(ruby.x + ruby.width / 2, base.x + base.width / 2)

    def test_align_left_right(self):
        left = by_text(layout_lyric(parse_ruby("青空《そ》"), 100, 0.5, "left", False, mono))
        self.assertAlmostEqual(left[("そ", True)].x, left[("青空", False)].x)
        right = by_text(layout_lyric(parse_ruby("青空《そ》"), 100, 0.5, "right", False, mono))
        b, r = right[("青空", False)], right[("そ", True)]
        self.assertAlmostEqual(r.x + r.width, b.x + b.width)

    def test_block_is_centred(self):
        glyphs = layout_lyric(parse_ruby("abc"), 10, 0.5, "center", False, mono)
        box = glyphs[0].box
        self.assertAlmostEqual(box[0] + box[2], 0)
        self.assertAlmostEqual(box[1] + box[3], 0)


class VerticalTests(unittest.TestCase):
    def test_stacked_with_ruby_on_right(self):
        glyphs = layout_lyric(parse_ruby("夢《ゆめ》の中"), 100, 0.5, "center", True, mono)
        base = [g for g in glyphs if not g.ruby]
        ruby = [g for g in glyphs if g.ruby]
        self.assertEqual([g.text for g in base], ["夢", "の", "中"])
        self.assertTrue(all(g.x == base[0].x for g in base))
        self.assertTrue(all(b.y < a.y for b, a in zip(base, base[1:])))
        self.assertTrue(all(r.x > base[0].x + 50 for r in ruby))
        self.assertEqual([g.text for g in ruby], ["ゆ", "め"])


class ProjectTests(unittest.TestCase):
    def make(self, **lyric):
        raw = {"project": {"bpm": 120, "fps": 30, "resolution": [320, 180]},
               "style": {"auto_chord_colors": False, "lyric_font_size": 20},
               "lyrics": [{"at": 0, "text": "焦《こ》がれ", **lyric}]}
        return compile_project(normalize(raw))

    def test_state_carries_layout_options(self):
        state = resolve_scene_state(self.make(vertical=True, ruby_align="left"), 30)
        self.assertEqual((state.lyric_vertical, state.lyric_align, state.lyric_position), (True, "left", (0.88, 0.5)))
        self.assertEqual(state.lyric_segments, (("焦", "こ"), ("がれ", None)))
        state = resolve_scene_state(self.make(position=[0.2, 0.3]), 30)
        self.assertEqual(state.lyric_position, (0.2, 0.3))

    def test_ruby_pixels_above_base(self):
        project = self.make()
        image = Renderer(project.resolution, project.doc["style"]).render(resolve_scene_state(project, 30))
        rows = [y for y in range(image.height) if any(image.getpixel((x, y)) != (0, 0, 0) for x in range(image.width))]
        # text sits around y = 0.82 * 180; ruby adds ink ~10+ px above the base line box
        self.assertLess(min(rows), 0.82 * 180 - 12)

    def test_validation(self):
        for bad in ({"ruby_align": "top"}, {"vertical": "yes"}, {"position": [2, 0]}):
            with self.subTest(bad=bad), self.assertRaises(ProjectError):
                self.make(**bad)
        with self.assertRaises(ProjectError):
            normalize({"style": {"ruby_scale": 0}})


if __name__ == "__main__":
    unittest.main()
