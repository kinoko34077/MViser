import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from mviser.guides import guide_shapes
from mviser.gui_state import load_recent, prune_missing, save_recent, update_recent
from mviser.preview_controller import PreviewController


class RecentTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.files = []
        for i in range(12):
            f = self.dir / f"p{i}.yaml"
            f.write_text("{}", encoding="utf-8")
            self.files.append(str(f.resolve()))

    def test_update_dedup_cap(self):
        recent = []
        for f in self.files:
            recent = update_recent(recent, f)
        self.assertEqual(len(recent), 10)
        self.assertEqual(recent[0], self.files[-1])
        recent = update_recent(recent, self.files[5])
        self.assertEqual(recent[0], self.files[5])
        self.assertEqual(len(recent), 10)
        self.assertEqual(recent.count(self.files[5]), 1)

    def test_prune_and_persist(self):
        missing = str(self.dir / "gone.yaml")
        self.assertEqual(prune_missing([self.files[0], missing]), [self.files[0]])
        store = self.dir / "state" / "recent.json"
        save_recent([self.files[0]], store)
        self.assertEqual(load_recent(store), [self.files[0]])
        store.write_text("not json", encoding="utf-8")
        self.assertEqual(load_recent(store), [])
        self.assertEqual(load_recent(self.dir / "none.json"), [])


class GuideTests(unittest.TestCase):
    def test_geometry(self):
        shapes = guide_shapes(1000, 500, 10, 20)
        self.assertIn((510.0, 20, 510.0, 520), shapes["centre"])
        self.assertIn((10 + 1000 / 3, 20, 10 + 1000 / 3, 520), shapes["thirds"])
        action, title = shapes["safe"]
        for got, want in ((action, (60, 45, 960, 495)), (title, (110, 70, 910, 470))):
            for g, w in zip(got, want):
                self.assertAlmostEqual(g, w)


class ChordColourToggleTests(unittest.TestCase):
    def test_preview_only(self):
        path = _path.PROJECT / "samples" / "sample.mvproj.yaml"
        before = path.read_text(encoding="utf-8")
        c = PreviewController(path)
        c.seek(10)
        coloured = c.render().getpixel((1, 1))
        c.chord_colors = False
        plain = c.render().getpixel((1, 1))
        self.assertEqual(plain, (0, 0, 0))
        self.assertNotEqual(coloured, plain)
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        from PIL import Image
        from mviser.video import FrameRange, write_frame_sequence
        frames = write_frame_sequence(c.project, Path(tempfile.mkdtemp()), FrameRange(10, 11))
        self.assertEqual(Image.open(frames[0]).getpixel((1, 1)), (0x1F, 0x3A, 0x5F))  # export keeps colours


if __name__ == "__main__":
    unittest.main()
