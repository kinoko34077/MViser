import unittest

import _path  # noqa: F401
from mviser.chord_engine import parse_chord
from mviser.motion import enter, pulse
from mviser.project_data import ProjectError, compile_project, normalize
from mviser.ruby import parse_ruby, strip_ruby
from mviser.scene import auto_chord_color, resolve_scene_state


def make(**overrides):
    raw = {
        "project": {"bpm": 120, "fps": 30, "resolution": [320, 180], "duration": "5:1"},
        "style": {"chord_colors": {"Em": "#112233"}},
        "motion": {"enter": "fade", "enter_duration": 0.2, "pulse": 0.1},
        "chords": [{"at": "1:1", "chord": "Em"}, {"at": "3:1", "chord": "C", "label": "C major", "motion": "cut"}],
        "lyrics": [{"at": 1.0, "text": "焦《こ》がれ"}],
    }
    raw.update(overrides)
    return compile_project(normalize(raw))


class MotionTests(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(enter("cut", 0.0, 0.2).opacity, 1.0)
        self.assertEqual(enter("fade", 0.0, 0.2).opacity, 0.0)
        self.assertEqual(enter("fade", 0.2, 0.2).opacity, 1.0)
        self.assertTrue(0 < enter("fade", 0.1, 0.2).opacity < 1)
        self.assertGreater(enter("slide", 0.0, 0.2).offset_x, 0)
        self.assertEqual(enter("slide", 1.0, 0.2).offset_x, 0)
        with self.assertRaises(ValueError):
            enter("spin", 0, 1)

    def test_pulse_peaks_on_beat(self):
        self.assertAlmostEqual(pulse(0.0, 0.1), 1.1)
        self.assertLess(pulse(0.5, 0.1), 1.1)
        self.assertEqual(pulse(0.3, 0), 1.0)


class RubyTests(unittest.TestCase):
    def test_narou_ruby(self):
        self.assertEqual(parse_ruby("焦《こ》がれ"), [("焦", "こ"), ("がれ", None)])
        self.assertEqual(strip_ruby("夢《ゆめ》の中"), "夢の中")
        self.assertEqual(parse_ruby("あの|青空《そら》へ"), [("あの", None), ("青空", "そら"), ("へ", None)])
        self.assertEqual(strip_ruby("plain"), "plain")


class SceneStateTests(unittest.TestCase):
    def test_compiled_frames(self):
        project = make()
        self.assertEqual(project.total_frames, 240)
        chords = project.tracks["chord"].events
        self.assertEqual([(e.start_frame, e.end_frame) for e in chords], [(0, 120), (120, 240)])

    def test_state_resolution(self):
        project = make()
        start = resolve_scene_state(project, 0)
        self.assertEqual(start.chord_label, "Em")
        self.assertEqual(start.background_color, "#112233")
        self.assertEqual(start.chord_motion.opacity, 0.0)
        self.assertAlmostEqual(start.chord_scale, 1.1)
        self.assertIsNone(start.lyric)

        mid = resolve_scene_state(project, 60)
        self.assertEqual(mid.chord_progress, 0.5)
        self.assertEqual(mid.chord_motion.opacity, 1.0)
        self.assertEqual(mid.lyric, "焦がれ")

        second = resolve_scene_state(project, 120)
        self.assertEqual(second.chord_label, "C major")
        self.assertEqual(second.chord_motion.opacity, 1.0)  # per-event cut
        self.assertEqual(second.background_color, auto_chord_color(parse_chord("C")))

    def test_auto_color_is_deterministic_and_minor_darker(self):
        self.assertEqual(auto_chord_color(parse_chord("C")), auto_chord_color(parse_chord("C7")))
        self.assertNotEqual(auto_chord_color(parse_chord("C")), auto_chord_color(parse_chord("Cm")))

    def test_default_duration_without_audio(self):
        project = make(project={"bpm": 120, "fps": 30})
        self.assertEqual(project.total_frames, 180)  # last start 4 s + one measure

    def test_validation_errors(self):
        bad = [
            {"chords": [{"at": "1:1", "chord": "H"}]},
            {"chords": [{"at": "0:1", "chord": "C"}]},
            {"events": [{"at": 0, "type": "image", "value": "x"}]},
            {"motion": {"enter": "spin"}},
            {"style": {"background_color": "red"}},
            {"project": {"resolution": [321, 180]}},
            {"unknown": 1},
            {"schema_version": 2},
        ]
        for override in bad:
            with self.subTest(override=override), self.assertRaises(ProjectError):
                make(**override)


if __name__ == "__main__":
    unittest.main()
