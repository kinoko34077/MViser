import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path

import yaml

import _path  # noqa: F401
from mviser.preview_controller import PreviewController

RAW = {
    "project": {"bpm": 120, "fps": 10, "resolution": [160, 90], "duration": "4:1", "key": "C"},
    "chords": [{"at": "1:1", "chord": "C"}, {"at": "2:1", "chord": "G7"}, {"at": "3:1", "chord": "Am"}],
    "lyrics": [{"at": "1:3", "text": "la"}],
    "subtitle_sets": [{"name": "en", "lyrics": [{"at": 0, "text": "hi"}]}],
}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "p.mvproj.yaml"
        self.write(RAW)
        self.c = PreviewController(self.path)

    def write(self, raw):
        self.path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    def test_seek_clamps(self):
        self.assertEqual(self.c.total_frames, 60)  # 3 measures * 2 s * 10 fps
        self.assertEqual(self.c.seek(-5), 0)
        self.assertEqual(self.c.seek(999), 59)
        self.assertEqual(self.c.seek_seconds(2.5), 25)
        self.assertEqual(self.c.step(-30), 0)

    def test_chord_jumps(self):
        self.c.seek(5)
        self.assertEqual(self.c.next_chord(), 20)
        self.assertEqual(self.c.next_chord(), 40)
        self.assertEqual(self.c.next_chord(), 40)  # no later chord
        self.assertEqual(self.c.prev_chord(), 20)
        self.c.seek(25)
        self.assertEqual(self.c.prev_chord(), 20)

    def test_readout(self):
        self.c.seek(25)
        r = self.c.readout()
        self.assertEqual((r["time"], r["position"], r["chord"], r["roman"]), ("00:02.50", "2:2.00", "G7", "V"))
        self.c.seek(10)
        self.assertEqual(self.c.readout()["lyric"], "la")

    def test_timeline_geometry(self):
        blocks = self.c.timeline_blocks(600)
        chords = [b for b in blocks if b["track"] == "chord"]
        self.assertEqual([(b["x0"], b["x1"], b["label"]) for b in chords],
                         [(0, 200, "C"), (200, 400, "G7"), (400, 600, "Am")])
        self.assertEqual(self.c.frame_at_x(300, 600), 30)
        self.assertEqual(self.c.x_at_frame(30, 600), 300)

    def test_render_fits_max_size(self):
        self.assertEqual(self.c.render((80, 80)).size, (80, 45))
        self.assertEqual(self.c.render().size, (160, 90))

    def test_reload_keeps_position_and_bad_file_keeps_last_good(self):
        self.c.seek(33)
        time.sleep(0.01)
        self.write({**RAW, "chords": RAW["chords"][:2]})
        os.utime(self.path, (time.time() + 5, time.time() + 5))
        self.assertTrue(self.c.reload_if_changed())
        self.assertEqual(self.c.frame, 33)
        self.assertEqual(len(self.c.project.tracks["chord"].events), 2)
        self.path.write_text("project: [broken", encoding="utf-8")
        os.utime(self.path, (time.time() + 10, time.time() + 10))
        self.assertTrue(self.c.reload_if_changed())
        self.assertIsNotNone(self.c.error)
        self.assertEqual(len(self.c.project.tracks["chord"].events), 2)
        self.assertFalse(self.c.reload_if_changed())  # no retry loop on the same broken save

    def test_subtitle_set_switch(self):
        self.assertEqual(self.c.subtitle_sets, ["default", "en"])
        self.assertIsNone(self.c.set_subtitle_set("en"))
        self.assertEqual(self.c.subtitle_set, "en")
        self.assertIsNotNone(self.c.set_subtitle_set("fr"))
        self.assertEqual(self.c.subtitle_set, "en")

    def test_empty_controller(self):
        c = PreviewController()
        self.assertIsNone(c.render())
        self.assertEqual(c.timeline_blocks(100), [])
        self.assertEqual(c.readout()["time"], "--:--.--")

    def test_export_frames(self):
        written = self.c.export_frames(self.dir / "frames")
        self.assertEqual(len(written), 60)


@unittest.skipIf(importlib.util.find_spec("tkinter") is None, "this Python build has no tkinter")
class GuiImportTests(unittest.TestCase):
    def test_gui_module_imports_without_display(self):
        import mviser.gui  # noqa: F401  (Tk is only created in run())


if __name__ == "__main__":
    unittest.main()
