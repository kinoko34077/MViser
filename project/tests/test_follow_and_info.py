import unittest

import _path  # noqa: F401
from mviser.project_data import ProjectError, compile_project, normalize
from mviser.project_info import project_info
from mviser.scene import resolve_scene_state
from mviser.time_format import format_time
from mviser.timeline import Tempo


def build(lyrics, style=None, sets=None):
    raw = {"project": {"bpm": 120, "fps": 10, "duration": 10}, "lyrics": lyrics}
    if style:
        raw["style"] = style
    if sets:
        raw["subtitle_sets"] = sets
    return compile_project(normalize(raw))


def payloads(project):
    return [e.payload for e in project.tracks["lyric"].events]


class FollowTests(unittest.TestCase):
    def test_explicit_follow_chain(self):
        p = payloads(build([
            {"at": 0, "text": "a", "vertical": True, "ruby_align": "left", "position": [0.2, 0.3]},
            {"at": 1, "text": "b", "vertical": "follow", "ruby_align": "follow", "position": "follow"},
            {"at": 2, "text": "c", "vertical": "follow", "ruby_align": "right"},
            {"at": 3, "text": "d", "ruby_align": "follow"},
        ]))
        self.assertEqual([x["vertical"] for x in p], [True, True, True, False])  # d: style default false
        self.assertEqual([x["ruby_align"] for x in p], ["left", "left", "right", "right"])
        self.assertEqual(p[1]["position"], [0.2, 0.3])
        self.assertNotIn("position", p[2])

    def test_style_default_follow_and_first_fallback(self):
        project = build([{"at": 0, "text": "a"}, {"at": 1, "text": "b", "vertical": True}, {"at": 2, "text": "c"}],
                        style={"vertical": "follow", "lyric_position": "follow"})
        self.assertEqual([x["vertical"] for x in payloads(project)], [False, True, True])
        state = resolve_scene_state(project, 25)
        self.assertTrue(state.lyric_vertical)
        self.assertEqual(state.lyric_position, (0.88, 0.5))

    def test_declaration_order_does_not_matter(self):
        p = payloads(build([{"at": 2, "text": "late", "vertical": "follow"}, {"at": 0, "text": "early", "vertical": True}]))
        self.assertEqual([(x["value"], x["vertical"]) for x in p], [("early", True), ("late", True)])

    def test_per_subtitle_set(self):
        sets = [{"name": "tate", "lyrics": [{"at": 0, "text": "x", "vertical": True},
                                            {"at": 1, "text": "y", "vertical": "follow"}]}]
        raw = {"project": {"bpm": 120, "fps": 10, "duration": 4}, "subtitle_sets": sets}
        p = payloads(compile_project(normalize(raw, ".", "tate")))
        self.assertEqual([x["vertical"] for x in p], [True, True])

    def test_invalid(self):
        with self.assertRaises(ProjectError):
            build([{"at": 0, "text": "a", "vertical": "sometimes"}])


class TimeFormatTests(unittest.TestCase):
    def test_modes(self):
        tempo = Tempo(120, 10, offset=0.5)
        self.assertEqual(format_time(25, tempo, "absolute"), "00:02.50")
        self.assertEqual(format_time(45, tempo, "tempo"), "3:1.00")   # 4.5 s - 0.5 = 8 beats = measure 3
        self.assertEqual(format_time(0, tempo, "tempo"), "-1.00b")
        self.assertEqual(format_time(7, tempo, "frames"), "f7")
        with self.assertRaises(ValueError):
            format_time(0, tempo, "bars")


class ProjectInfoTests(unittest.TestCase):
    def test_rows(self):
        project = build([{"at": 0, "text": "a"}])
        info = dict(project_info(project))
        self.assertEqual(info["Lyric events"], "1")
        self.assertEqual(info["FPS / resolution"], "10 / 1920x1080")
        self.assertIn("100 frames", info["Duration"])
        self.assertEqual(info["Audio"], "-")


if __name__ == "__main__":
    unittest.main()
