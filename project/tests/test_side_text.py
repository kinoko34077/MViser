import unittest

import _path  # noqa: F401
from mviser.project_data import ProjectError, compile_project, normalize
from mviser.render_engine import Renderer
from mviser.scene import resolve_scene_state
from mviser.side_text import side_centres, tile_offsets


class TilingTests(unittest.TestCase):
    def assert_covers(self, offsets, strip, unit, spacing):
        self.assertTrue(offsets)
        self.assertLessEqual(offsets[0], spacing + 1e-9)  # any leading gap is at most one spacing
        for a, b in zip(offsets, offsets[1:]):
            self.assertAlmostEqual(b - a, unit + spacing)
        self.assertGreaterEqual(offsets[-1] + unit + spacing, strip)

    def test_coverage_for_any_scroll(self):
        for scroll in (0, 13.5, 99, 250, -40):
            with self.subTest(scroll=scroll):
                self.assert_covers(tile_offsets(300, 80, 20, scroll), 300, 80, 20)

    def test_scroll_is_periodic(self):
        self.assertEqual(tile_offsets(300, 80, 20, 30), tile_offsets(300, 80, 20, 130))

    def test_degenerate(self):
        self.assertEqual(tile_offsets(0, 80, 20, 0), [])
        self.assertEqual(tile_offsets(100, 0, 0, 0), [])

    def test_side_centres(self):
        self.assertEqual(side_centres("both", 1000, 0.05), [50.0, 950.0])
        self.assertEqual(side_centres("none", 1000, 0.05), [])


class ProjectTests(unittest.TestCase):
    def make(self, lyric=None, side_text=None):
        raw = {"project": {"bpm": 120, "fps": 10, "resolution": [200, 100], "duration": 4},
               "style": {"auto_chord_colors": False, "lyric_font_size": 10,
                         "side_text": side_text or {"size": 12, "opacity": 1.0, "scroll": 20}},
               "lyrics": [{"at": 0, "text": "焦《こ》がれ", **(lyric or {})}]}
        return compile_project(normalize(raw))

    def test_state(self):
        state = resolve_scene_state(self.make({"repeat_side": "left"}), 10)
        self.assertEqual((state.side, state.side_text, state.side_scroll), ("left", "焦がれ", 20.0))
        state = resolve_scene_state(self.make({"repeat_side": "both", "loop_text": "LOOP"}), 0)
        self.assertEqual((state.side_text, state.side_scroll), ("LOOP", 0.0))
        self.assertEqual(resolve_scene_state(self.make(), 0).side, "none")

    def test_ink_only_in_chosen_margin(self):
        project = self.make({"repeat_side": "left", "loop_text": "AB"})
        image = Renderer(project.resolution, project.doc["style"]).render(resolve_scene_state(project, 20))
        ink = lambda x0, x1: any(image.getpixel((x, y)) != (0, 0, 0) for x in range(x0, x1) for y in range(0, 60))
        self.assertTrue(ink(0, 30))
        self.assertFalse(ink(170, 200))

    def test_validation(self):
        with self.assertRaises(ProjectError):
            self.make({"repeat_side": "top"})
        for bad in ({"side": "up"}, {"opacity": 2}, {"size": "big"}, {"colour": 1}, {"vertical": 1}):
            with self.subTest(bad=bad), self.assertRaises(ProjectError):
                self.make(side_text=bad)


if __name__ == "__main__":
    unittest.main()
