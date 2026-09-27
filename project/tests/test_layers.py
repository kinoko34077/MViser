import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml
from PIL import Image

import _path  # noqa: F401
from make_click_wav import make_click_wav
from mviser.cli import main
from mviser.project_data import load_project
from mviser.render_engine import Renderer
from mviser.scene import resolve_scene_state
from mviser.video import FrameRange, find_ffmpeg, write_frame_sequence, write_video

RAW = {"project": {"bpm": 120, "fps": 10, "resolution": [160, 90], "duration": 1},
       "style": {"background_color": "#102030", "auto_chord_colors": False, "chord_font_size": 40,
                 "lyric_font_size": 14},
       "motion": {"enter": "cut", "pulse": 0},
       "audio": {"path": "a.wav"},
       "chords": [{"at": 0, "chord": "C"}], "lyrics": [{"at": 0, "text": "la la"}]}


def probe(path):
    return subprocess.run([find_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr


class LayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        make_click_wav(cls.dir / "a.wav", 120, 1.0)
        (cls.dir / "p.yaml").write_text(yaml.safe_dump(RAW), encoding="utf-8")
        cls.project = load_project(cls.dir / "p.yaml")
        cls.state = resolve_scene_state(cls.project, 5)
        cls.renderer = Renderer(cls.project.resolution, cls.project.doc["style"], cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def alpha_rows(self, image):
        a = image.getchannel("A")
        return [y for y in range(image.height) if a.crop((0, y, image.width, y + 1)).getextrema()[1] > 0]

    def test_default_is_unchanged_opaque(self):
        rgb = self.renderer.render(self.state)
        self.assertEqual(rgb.mode, "RGB")
        self.assertEqual(rgb.getpixel((0, 0)), (0x10, 0x20, 0x30))
        self.assertEqual(rgb.tobytes(), self.renderer.render_rgba(self.state).convert("RGB").tobytes())

    def test_transparent_layers(self):
        chords = self.renderer.render_rgba(self.state, ("chords",))
        lyrics = self.renderer.render_rgba(self.state, ("lyrics",))
        self.assertEqual(chords.getpixel((0, 0))[3], 0)
        chord_rows, lyric_rows = self.alpha_rows(chords), self.alpha_rows(lyrics)
        self.assertTrue(chord_rows and lyric_rows)
        self.assertLess(max(chord_rows), min(lyric_rows))  # chord ink above lyric ink, no overlap
        with self.assertRaises(ValueError):
            self.renderer.render_rgba(self.state, ("sky",))

    def test_png_sequence_rgba_without_background(self):
        out = write_frame_sequence(self.project, self.dir / "f", FrameRange(0, 2), layers=("lyrics",))
        self.assertEqual(Image.open(out[0]).mode, "RGBA")
        out = write_frame_sequence(self.project, self.dir / "g", FrameRange(0, 2))
        self.assertEqual(Image.open(out[0]).mode, "RGB")

    def test_alpha_video_formats(self):
        for fmt, ext, pix in (("prores4444", ".mov", "yuva444p"), ("webm", ".webm", "yuva420p")):
            with self.subTest(fmt=fmt):
                out = write_video(self.project, self.dir / f"o{ext}", FrameRange(0, 5), layers=("chords", "lyrics"),
                                  fmt=fmt)
                info = probe(out)
                if fmt == "webm":  # VP9 alpha lives in a side stream; ffmpeg reports it as alpha_mode
                    self.assertIn("alpha_mode", info.lower())
                else:
                    self.assertIn(pix, info)
        with self.assertRaises(ValueError):
            write_video(self.project, self.dir / "x.avi", FrameRange(0, 1), fmt="avi")

    def test_cli_split_layers(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = main(["render", str(self.dir / "p.yaml"), "--frames", str(self.dir / "split"),
                         "--split-layers", "--layers", "chords,lyrics"])
        self.assertEqual(code, 0)
        counts = {n: len(list((self.dir / "split" / n).glob("*.png"))) for n in ("chords", "lyrics")}
        self.assertEqual(counts, {"chords": 10, "lyrics": 10})
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["render", str(self.dir / "p.yaml"), "--frames", str(self.dir / "z"),
                                   "--layers", "sky"]), 2)


if __name__ == "__main__":
    unittest.main()
