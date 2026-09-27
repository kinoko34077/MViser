import importlib.util
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from mviser.global_settings import GlobalSettingsError, global_path, load_global, validate_global
from mviser.project_data import load_project
from mviser.settings_model import FIELDS, SettingsDocument, SettingsError, format_value, parse_value

F = {f.key: f for f in FIELDS}

PROJECT = """# my song
project:
  title: "Song"   # keep me
  bpm: 140
motion:
  pulse: 0.1
chords:
  - {at: 0, chord: C}
"""


class GlobalTests(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(global_path({"MVISER_GLOBAL": "/x/g.yaml"}, "linux"), Path("/x/g.yaml"))
        self.assertEqual(global_path({"APPDATA": "C:/AD"}, "win32"), Path("C:/AD/MViser/global.yaml"))
        self.assertEqual(global_path({"XDG_CONFIG_HOME": "/cfg"}, "linux"), Path("/cfg/mviser/global.yaml"))
        self.assertEqual(global_path({}, "darwin").parts[-3:], ("Application Support", "MViser", "global.yaml"))

    def test_validation(self):
        self.assertEqual(validate_global(None), {})
        for bad in ([], {"chords": {}}, {"project": {"bpm": 1}}, {"style": 3}):
            with self.subTest(bad=bad), self.assertRaises(GlobalSettingsError):
                validate_global(bad)
        self.assertEqual(load_global(Path(tempfile.mkdtemp()) / "none.yaml"), {})


class LayeringTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "p.mvproj.yaml"
        self.path.write_text(PROJECT, encoding="utf-8")
        self.glob = {"style": {"text_color": "#FFEE00"}, "motion": {"pulse": 0.5, "enter": "slide"}}

    def test_loader_layers(self):
        project = load_project(self.path, global_doc=self.glob)
        self.assertEqual(project.doc["style"]["text_color"], "#FFEE00")    # global
        self.assertEqual(project.doc["motion"]["pulse"], 0.1)              # project beats global
        self.assertEqual(project.doc["motion"]["enter"], "slide")          # global beats builtin
        self.assertEqual(project.doc["style"]["background_color"], "#000000")  # builtin

    def test_effective_sources(self):
        doc = SettingsDocument(self.path, "project", self.glob)
        self.assertEqual(doc.effective(F["motion.pulse"]), (0.1, "project"))
        self.assertEqual(doc.effective(F["motion.enter"]), ("slide", "global"))
        self.assertEqual(doc.effective(F["style.background_color"]), ("#000000", "builtin"))

    def test_edit_preserves_comments_and_writes_only_overrides(self):
        doc = SettingsDocument(self.path, "project", self.glob)
        doc.set(F["style.lyric_font_size"], 50)
        doc.reset(F["motion.pulse"])
        doc.save()
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("# my song", text)
        self.assertIn("# keep me", text)
        self.assertIn("lyric_font_size: 50", text)
        self.assertNotIn("motion", text)          # emptied section pruned
        self.assertNotIn("background_color", text)  # inherited values not written
        self.assertEqual(SettingsDocument(self.path, "project", self.glob).effective(F["motion.pulse"]),
                         (0.5, "global"))

    def test_invalid_rejected_with_field_path(self):
        doc = SettingsDocument(self.path, "project")
        doc.set(F["motion.enter"], "spin")
        with self.assertRaisesRegex(SettingsError, "motion.enter"):
            doc.save()
        self.assertIn("pulse: 0.1", self.path.read_text(encoding="utf-8"))  # file untouched

    def test_global_layer(self):
        gpath = self.dir / "cfg" / "global.yaml"
        doc = SettingsDocument(gpath, "global")
        self.assertNotIn("project.bpm", [f.key for f in doc.fields()])
        doc.set(F["project.fps"], 24)
        doc.save()
        self.assertEqual(load_global(gpath), {"project": {"fps": 24}})


class ParseTests(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(parse_value(F["project.resolution"], "1280x720"), [1280, 720])
        self.assertEqual(format_value(F["project.resolution"], [1280, 720]), "1280x720")
        self.assertEqual(parse_value(F["style.lyric_position"], "0.5, 0.8"), [0.5, 0.8])
        self.assertIsNone(parse_value(F["style.lyric_position"], ""))
        self.assertIs(parse_value(F["style.vertical"], "true"), True)
        for key, bad in (("project.fps", "x"), ("motion.enter", "spin"), ("style.vertical", "maybe")):
            with self.subTest(key=key), self.assertRaises(SettingsError):
                parse_value(F[key], bad)


@unittest.skipIf(importlib.util.find_spec("tkinter") is None, "this Python build has no tkinter")
class WindowImportTests(unittest.TestCase):
    def test_imports(self):
        import mviser.settings_window  # noqa: F401


if __name__ == "__main__":
    unittest.main()
