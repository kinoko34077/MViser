import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from mviser.project_data import ProjectError, normalize, resolve_project_resource


class ProjectAssetPathAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        (self.root / "assets").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_relative_resource_resolves_inside_project(self):
        expected = (self.root / "assets" / "song.wav").resolve()
        self.assertEqual(
            resolve_project_resource(self.root, "assets/song.wav", "audio.path"),
            expected,
        )
        self.assertEqual(
            resolve_project_resource(self.root, "assets/../assets/song.wav", "audio.path"),
            expected,
        )

    def test_absolute_drive_rooted_and_parent_escape_fail_closed(self):
        cases = (
            "/tmp/outside.wav",
            "/assets/song.wav",
            "\\assets\\song.wav",
            "C:\\outside\\song.wav",
            "\\\\server\\share\\song.wav",
            "../outside.wav",
            "assets/../../outside.wav",
            "..\\outside.wav",
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ProjectError):
                resolve_project_resource(self.root, value, "audio.path")

    def test_project_audio_path_rejects_empty_absolute_and_parent_escape(self):
        for value in ("", "/tmp/audio.wav", "../audio.wav", "C:\\audio.wav"):
            with self.subTest(value=value), self.assertRaisesRegex(ProjectError, "audio.path"):
                normalize({"audio": {"path": value}}, self.root)

    def test_import_path_rejects_absolute_and_parent_escape_before_importer_io(self):
        for value in ("/tmp/song.mid", "../song.mid", "C:\\song.mid"):
            raw = {"imports": [{"format": "midi", "path": value}]}
            with self.subTest(value=value), self.assertRaisesRegex(ProjectError, r"imports\[0\]\.path"):
                normalize(raw, self.root)

    def test_project_and_subtitle_font_paths_are_contained(self):
        for value in ("", "../outside.ttf"):
            with self.subTest(value=value), self.assertRaisesRegex(ProjectError, "style.font_path"):
                normalize({"style": {"font_path": value}}, self.root)

        raw = {
            "subtitle_sets": [{
                "name": "alt",
                "style": {"font_path": "C:\\Windows\\Fonts\\font.ttf"},
                "lyrics": [],
            }]
        }
        with self.assertRaisesRegex(ProjectError, r"subtitle_sets\[0\]\.style\.font_path"):
            normalize(raw, self.root)

    def test_normal_project_relative_asset_declarations_remain_supported(self):
        doc = normalize(
            {
                "audio": {"path": "assets/song.wav"},
                "style": {"font_path": "assets/font.ttf"},
            },
            self.root,
        )
        self.assertEqual(doc["audio"]["path"], "assets/song.wav")
        self.assertEqual(doc["style"]["font_path"], "assets/font.ttf")

    def test_user_local_global_font_path_is_not_project_document_authority(self):
        external = str((Path(self.tmp.name) / "global-font.ttf").resolve())
        doc = normalize({}, self.root, global_doc={"style": {"font_path": external}})
        self.assertEqual(doc["style"]["font_path"], external)


if __name__ == "__main__":
    unittest.main()
