import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import yaml

import _path  # noqa: F401
from mviser.cli import main
from mviser.project_data import ProjectError, compile_project, normalize
from mviser.scene import resolve_scene_state

RAW = {
    "project": {"bpm": 120, "fps": 30, "resolution": [320, 180], "duration": 4},
    "style": {"lyric_font_size": 40},
    "chords": [{"at": 0, "chord": "C"}, {"at": 2, "chord": "G"}],
    "lyrics": [{"at": 0, "text": "焦《こ》がれ"}],
    "subtitle_sets": [
        {"name": "en", "lyrics": [{"at": 1, "text": "Longing"}]},
        {"name": "tate", "lyrics": [{"at": 0, "text": "夢"}], "style": {"vertical": True, "lyric_font_size": 30}},
    ],
}


def build(raw=RAW, name=None):
    return compile_project(normalize(raw, ".", name))


class SubtitleSetTests(unittest.TestCase):
    def test_default_is_legacy_lyrics(self):
        project = build()
        self.assertEqual(project.doc["subtitle_sets"], ["default", "en", "tate"])
        self.assertEqual(project.doc["active_subtitle_set"], "default")
        self.assertEqual(project.tracks["lyric"].events[0].payload["text"], "焦がれ")

    def test_switch_changes_only_lyrics(self):
        base, en = build(), build(name="en")
        chords = lambda p: [(e.start_frame, e.end_frame, e.payload["display"]) for e in p.tracks["chord"].events]
        self.assertEqual(chords(base), chords(en))
        self.assertEqual(en.tracks["lyric"].events[0].start_frame, 30)
        self.assertEqual(en.tracks["lyric"].events[0].payload["text"], "Longing")

    def test_set_style_applies_only_to_that_set(self):
        tate = build(name="tate")
        self.assertTrue(resolve_scene_state(tate, 10).lyric_vertical)
        self.assertEqual(tate.doc["style"]["lyric_font_size"], 30)
        self.assertEqual(build(name="en").doc["style"]["lyric_font_size"], 40)

    def test_project_level_selection_and_errors(self):
        raw = dict(RAW, project={**RAW["project"], "subtitle_set": "en"})
        self.assertEqual(build(raw).doc["active_subtitle_set"], "en")
        with self.assertRaisesRegex(ProjectError, "available"):
            build(name="fr")
        bad_style = dict(RAW, subtitle_sets=[{"name": "x", "lyrics": [], "style": {"chord_font_size": 9}}])
        with self.assertRaisesRegex(ProjectError, r"subtitle_sets\[0\]\.style\.chord_font_size"):
            build(bad_style)
        dup = dict(RAW, subtitle_sets=[{"name": "default", "lyrics": []}])
        with self.assertRaises(ProjectError):
            build(dup)

    def test_no_lyrics_at_all(self):
        project = build({"chords": [{"at": 0, "chord": "C"}]})
        self.assertEqual(project.doc["subtitle_sets"], [])
        self.assertIsNone(resolve_scene_state(project, 0).lyric)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "p.mvproj.yaml"
        self.path.write_text(yaml.safe_dump(RAW, allow_unicode=True), encoding="utf-8")

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main(list(argv))
        return code, out.getvalue()

    def test_inspect_lists_and_selects(self):
        code, out = self.run_cli("inspect", str(self.path), "--subtitle-set", "en")
        data = json.loads(out)
        self.assertEqual((code, data["active_subtitle_set"], data["subtitle_sets"]), (0, "en", ["default", "en", "tate"]))
        self.assertEqual(self.run_cli("inspect", str(self.path), "--subtitle-set", "fr")[0], 2)

    def test_render_all_sets_to_frame_dirs(self):
        code, out = self.run_cli("render", str(self.path), "--frames", str(self.dir / "frames"),
                                 "--start", "0", "--end", "0.1", "--all-subtitle-sets")
        self.assertEqual(code, 0)
        for name in ("default", "en", "tate"):
            self.assertEqual(len(list((self.dir / "frames" / name).glob("*.png"))), 3)


if __name__ == "__main__":
    unittest.main()
