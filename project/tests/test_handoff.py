import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import _path  # noqa: F401
from make_click_wav import make_click_wav
from mviser.cli import main
from mviser.handoff import HandoffError, build_exo, build_jsx, handoff, render_template
from mviser.project_data import load_project

RAW = {"project": {"title": "Test \"Song\"", "bpm": 120, "fps": 10, "resolution": [64, 36], "duration": 1},
       "audio": {"path": "a.wav"}, "chords": [{"at": 0, "chord": "C"}], "lyrics": [{"at": 0, "text": "焦《こ》がれ"}]}


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        make_click_wav(cls.dir / "a.wav", 120, 1.0)
        (cls.dir / "p.yaml").write_text(yaml.safe_dump(RAW, allow_unicode=True), encoding="utf-8")
        cls.project = load_project(cls.dir / "p.yaml")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_exo_text(self):
        files = [self.dir / "x_background.mov", self.dir / "x_lyrics.mov"]
        text = build_exo(self.project, files, self.dir / "a.wav")
        self.assertTrue(text.startswith("[exedit]\nwidth=64\nheight=36\nrate=10\n"))
        self.assertIn("length=10", text)
        self.assertEqual(text.count("_name=動画ファイル"), 2)
        self.assertEqual(text.count("_name=音声ファイル"), 1)
        self.assertIn("[0]\nstart=1\nend=10\nlayer=2", text)   # background on the bottom row
        self.assertIn("[1]\nstart=1\nend=10\nlayer=1", text)
        self.assertIn(str((self.dir / "x_lyrics.mov").resolve()), text)

    def test_jsx_text(self):
        text = build_jsx(self.project, [self.dir / "b.mov"], None)
        self.assertIn('addComp("Test \\"Song\\"", 64, 36, 1.0, 1.000000, 10)', text)
        self.assertIn((self.dir / "b.mov").resolve().as_posix(), text)
        self.assertIn("for (var i = 0; i < files.length; i++) {", text)  # JS braces untouched

    def test_template_override_and_errors(self):
        custom = self.dir / "custom.exo"
        custom.write_text("[exedit]\nwidth={width}\n{objects}\n", encoding="utf-8")
        self.assertTrue(build_exo(self.project, [], None, custom).startswith("[exedit]\nwidth=64\n"))
        bad = self.dir / "bad.exo"
        bad.write_text("{nope}", encoding="utf-8")
        with self.assertRaisesRegex(HandoffError, "nope"):
            build_exo(self.project, [], None, bad)
        with self.assertRaises(HandoffError):
            render_template("{a", {})

    def test_full_handoff_files(self):
        out = self.dir / "handoff"
        result = handoff(self.project, out, "song", "webm", ("chords", "lyrics"))
        for key in ("layer_chords", "layer_lyrics", "exo", "jsx", "audio"):
            self.assertTrue(Path(result[key]).exists(), key)
        raw = result["exo"].read_bytes()
        self.assertIn(b"\r\n", raw)
        self.assertIn("動画ファイル".encode("cp932"), raw)
        with self.assertRaises(HandoffError):
            handoff(self.project, out, "song", "mp4")

    def test_cli(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = main(["handoff", str(self.dir / "p.yaml"), "-o", str(self.dir / "cli"), "--format", "webm",
                         "--layers", "lyrics"])
        self.assertEqual(code, 0)
        self.assertIn("exo:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
