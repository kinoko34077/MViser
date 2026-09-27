import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from mviser.lyric_editor import LyricDocument, LyricEditError, frame_to_position
from mviser.project_data import load_project
from mviser.timeline import Tempo

SRC = """# song
project: {bpm: 135, fps: 30, duration: "9:1"}   # tempo
chords:
  - {at: "1:1", chord: Em}
lyrics:
  - at: "2:1"
    text: "焦《こ》がれ"   # first line
subtitle_sets:
  - name: en
    lyrics:
      - {at: 4.0, text: Longing}
"""


class PositionTests(unittest.TestCase):
    def test_round_trip(self):
        for bpm, fps, offset in ((135, 30, 0.0), (120, 24, 0.37), (97, 60, 0.0)):
            tempo = Tempo(bpm, fps, offset)
            for frame in (0, 1, 17, 107, 213, 999):
                for mode in ("tempo", "seconds"):
                    with self.subTest(bpm=bpm, frame=frame, mode=mode):
                        at = frame_to_position(tempo, frame, mode)
                        self.assertEqual(tempo.seconds_to_frame(tempo.to_seconds(at)), frame)
        self.assertEqual(frame_to_position(Tempo(120, 30), 60), "2:1")
        self.assertIsInstance(frame_to_position(Tempo(120, 30), 60, "seconds"), float)


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "p.mvproj.yaml"
        self.path.write_text(SRC, encoding="utf-8")

    def test_default_set_edits(self):
        doc = LyricDocument(self.path)
        self.assertEqual(doc.subtitle_set, "default")
        self.assertEqual([r.frame for r in doc.rows()], [53])  # 2:1 at 135 bpm
        new = doc.add(0, "はじまり")
        self.assertEqual(new, 0)  # sorted before the existing line
        doc.update(1, text="焦《こ》がれて")
        doc.update(0, frame=213)
        self.assertEqual([r.text for r in doc.rows()], ["焦《こ》がれて", "はじまり"])
        doc.save()
        text = self.path.read_text(encoding="utf-8")
        for keep in ("# song", "# tempo", "# first line", "name: en", "Longing"):
            self.assertIn(keep, text)
        project = load_project(self.path)
        self.assertEqual([e.start_frame for e in project.tracks["lyric"].events], [53, 213])

    def test_named_set_only(self):
        doc = LyricDocument(self.path, "en")
        doc.add(30, "Hello", mode="seconds")
        doc.delete(1)  # "Longing" sorted after
        doc.save()
        en = load_project(self.path, "en").tracks["lyric"].events
        self.assertEqual([(e.start_frame, e.payload["text"]) for e in en], [(30, "Hello")])
        default = load_project(self.path).tracks["lyric"].events
        self.assertEqual([e.payload["text"] for e in default], ["焦がれ"])

    def test_errors_do_not_write(self):
        doc = LyricDocument(self.path)
        with self.assertRaises(LyricEditError):
            doc.add(0, "  ")
        with self.assertRaises(LyricEditError):
            doc.delete(5)
        doc.data["project"]["fps"] = "x"
        with self.assertRaises(LyricEditError):
            doc.save()
        self.assertEqual(self.path.read_text(encoding="utf-8"), SRC)
        with self.assertRaises(LyricEditError):
            LyricDocument(self.path, "fr")

    def test_project_without_lyrics(self):
        self.path.write_text("project: {bpm: 120, fps: 30}\nchords: [{at: 0, chord: C}]\n", encoding="utf-8")
        doc = LyricDocument(self.path)
        doc.add(30, "first")
        doc.save()
        self.assertEqual(load_project(self.path).tracks["lyric"].events[0].start_frame, 30)


if __name__ == "__main__":
    unittest.main()


class UnquotedPositionTests(unittest.TestCase):
    def test_unquoted_measure_beat_is_not_base60(self):
        path = Path(tempfile.mkdtemp()) / "p.yaml"
        path.write_text("project: {bpm: 120, fps: 30}\nchords:\n  - {at: 3:1, chord: C}\n  - {at: 4:2.5, chord: G}\n",
                        encoding="utf-8")
        events = load_project(path).tracks["chord"].events
        self.assertEqual([e.start_frame for e in events], [120, 202])  # 4.0 s and 6.75 s, not 181 s / 242.5 s
