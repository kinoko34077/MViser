import unittest

import _path  # noqa: F401
from mviser.timeline import Event, Tempo, TimelineError, build_track


class TempoTests(unittest.TestCase):
    def test_seconds_to_frame_examples(self):
        tempo = Tempo(120, 30)
        self.assertEqual([tempo.seconds_to_frame(s) for s in (0.0, 1.0, 4.5)], [0, 30, 135])

    def test_measure_beat_conversion_fixed_4_4(self):
        tempo = Tempo(120, 30)  # beat = 0.5 s, measure = 2 s
        self.assertEqual(tempo.to_seconds("1:1"), 0.0)
        self.assertEqual(tempo.to_seconds("1:3"), 1.0)
        self.assertEqual(tempo.to_seconds("3:1"), 4.0)
        self.assertEqual(tempo.to_seconds("2:2.5"), 2.75)
        self.assertEqual(tempo.to_seconds({"measure": 3, "beat": 1}), 4.0)
        self.assertEqual(tempo.to_seconds(1.25), 1.25)

    def test_offset_applies_to_musical_positions_only(self):
        tempo = Tempo(120, 30, offset=0.5)
        self.assertEqual(tempo.to_seconds("1:1"), 0.5)
        self.assertEqual(tempo.to_seconds(0.25), 0.25)

    def test_issue_example_135bpm(self):
        tempo = Tempo(135, 30)
        self.assertEqual(tempo.seconds_to_frame(tempo.to_seconds("3:1")), 107)  # 8 beats * 60/135 = 3.555.. s * 30fps

    def test_invalid_positions(self):
        tempo = Tempo(120, 30)
        for bad in ("0:1", "1:0", "abc", -1, True):
            with self.subTest(bad=bad), self.assertRaises(TimelineError):
                tempo.to_seconds(bad)
        with self.assertRaises(TimelineError):
            Tempo(0, 30)

    def test_beat_phase(self):
        tempo = Tempo(120, 30, offset=0.1)
        self.assertAlmostEqual(tempo.beat_phase(0.1), 0.0)
        self.assertAlmostEqual(tempo.beat_phase(0.35), 0.5)
        self.assertAlmostEqual(tempo.beat_phase(0.6), 0.0)
        self.assertAlmostEqual(tempo.beat_position(1.1), 2.0)


class TrackTests(unittest.TestCase):
    def setUp(self):
        self.track = build_track("chord", [(60, {"v": "C"}), (0, {"v": "Em"})], 120)

    def test_boundaries_are_half_open(self):
        self.assertIsNone(build_track("chord", [(10, {"v": "C"})], 20).active(9))
        self.assertEqual(self.track.active(0).payload["v"], "Em")
        self.assertEqual(self.track.active(59).payload["v"], "Em")
        self.assertEqual(self.track.active(60).payload["v"], "C")
        self.assertEqual(self.track.active(119).payload["v"], "C")
        self.assertIsNone(self.track.active(120))

    def test_local_progress(self):
        event = self.track.active(90)
        self.assertEqual(event.local_frame(90), 30)
        self.assertEqual(event.progress(60), 0.0)
        self.assertEqual(event.progress(90), 0.5)
        self.assertEqual(Event(5, 5, "x").progress(5), 1.0)

    def test_same_frame_later_declaration_wins(self):
        track = build_track("chord", [(0, {"v": "A"}), (0, {"v": "B"})], 10)
        self.assertEqual(track.active(0).payload["v"], "B")

    def test_explicit_duration_ends_early(self):
        track = build_track("lyric", [(0, {"v": "a", "duration_frames": 5}), (20, {"v": "b"})], 30)
        self.assertIsNone(track.active(5))
        self.assertEqual(track.active(20).payload["v"], "b")


if __name__ == "__main__":
    unittest.main()
