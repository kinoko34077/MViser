import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from make_click_wav import make_click_wav
from mviser.cli import main
from mviser.project_data import load_project
from mviser.render_engine import Renderer
from mviser.scene import resolve_scene_state
from mviser.video import FrameRange, find_ffmpeg, write_frame_sequence, write_video

SAMPLE = _path.PROJECT / "samples" / "sample.mvproj.yaml"


def probe(path: Path) -> dict:
    """Parse stream info from `ffmpeg -i` (ffprobe is not always bundled)."""
    out = subprocess.run([find_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    return {"video": "Video: h264" in out, "audio": "Audio: aac" in out, "raw": out}


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copy(SAMPLE, cls.tmp / "sample.mvproj.yaml")
        make_click_wav(cls.tmp / "click.wav", 135, 16)
        cls.project = load_project(cls.tmp / "sample.mvproj.yaml")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def render(self, frame):
        renderer = Renderer(self.project.resolution, self.project.doc["style"], self.project.base_dir)
        return renderer.render(resolve_scene_state(self.project, frame))

    def test_selected_frame_rendering_is_deterministic(self):
        a, b = self.render(100), self.render(100)
        self.assertEqual(a.size, (1280, 720))
        self.assertEqual(a.tobytes(), b.tobytes())
        self.assertEqual(a.getpixel((2, 2)), (0x1F, 0x3A, 0x5F))  # Em configured colour

    def test_chord_switch_changes_background(self):
        switch = self.project.tracks["chord"].events[1].start_frame
        self.assertEqual(switch, 107)
        self.assertEqual(self.render(switch - 1).getpixel((2, 2)), (0x1F, 0x3A, 0x5F))
        self.assertNotEqual(self.render(switch).getpixel((2, 2)), (0x1F, 0x3A, 0x5F))

    def test_fade_in_changes_label_over_time(self):
        first = self.render(0).crop((440, 200, 840, 400)).getextrema()
        later = self.render(15).crop((440, 200, 840, 400)).getextrema()
        self.assertEqual(first[0][1], 0x1F)  # label fully transparent at event start
        self.assertGreater(later[0][1], 0x1F)  # visible after enter_duration

    def test_frame_sequence(self):
        out = self.tmp / "frames"
        written = write_frame_sequence(self.project, out, FrameRange(210, 216))
        self.assertEqual([p.name for p in written][0], "frame_000210.png")
        self.assertEqual(len(written), 6)

    def test_mp4_with_audio_end_to_end(self):
        out = self.tmp / "out.mp4"
        write_video(self.project, out, FrameRange.from_seconds(self.project, 3.0, 5.0))
        info = probe(out)
        self.assertTrue(info["video"], info["raw"])
        self.assertTrue(info["audio"], info["raw"])
        self.assertIn("Duration: 00:00:02.0", info["raw"])

    def test_cli_inspect_and_frame(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["inspect", str(self.tmp / "sample.mvproj.yaml")]), 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["total_frames"], 427)
        chords = data["tracks"]["chord"]
        self.assertEqual([e["value"] for e in chords], ["Em", "C", "D", "v7"])
        self.assertEqual([e["display"] for e in chords], ["Em", "C", "D", "Bm7"])
        self.assertEqual([e["analysis"]["roman"] for e in chords], ["i", "VI", "VII", "v"])
        png = self.tmp / "f.png"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["frame", str(self.tmp / "sample.mvproj.yaml"), "--time", "4.0", "-o", str(png)]), 0)
        self.assertTrue(png.exists())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["inspect", str(self.tmp / "missing.yaml")]), 2)


if __name__ == "__main__":
    unittest.main()
