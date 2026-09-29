import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401
from mviser.durable_io import atomic_write_text
from mviser.lyric_editor import LyricDocument, LyricEditError
from mviser.project_data import save_project
from mviser.settings_model import FIELDS, SettingsDocument, SettingsError

F = {field.key: field for field in FIELDS}
PROJECT = """# durable project
project: {title: Song, bpm: 120, fps: 30, duration: 4}
motion: {pulse: 0.1}
chords: [{at: 0, chord: C}]
lyrics: [{at: 0, text: hello}]
"""


class AtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "state.yaml"
        self.path.write_text("old: true\n", encoding="utf-8")

    def temp_files(self):
        return list(self.dir.glob(f".{self.path.name}.*.tmp"))

    def test_fsync_failure_preserves_previous_file_and_cleans_stage(self):
        with patch("mviser.durable_io.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                atomic_write_text(self.path, "new: true\n")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "old: true\n")
        self.assertEqual(self.temp_files(), [])

    def test_replace_failure_preserves_previous_file_and_cleans_stage(self):
        with patch("mviser.durable_io.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                atomic_write_text(self.path, "new: true\n")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "old: true\n")
        self.assertEqual(self.temp_files(), [])

    def test_success_publishes_complete_file_and_cleans_stage(self):
        atomic_write_text(self.path, "new: true\n")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "new: true\n")
        self.assertEqual(self.temp_files(), [])


class SaveEntryPointTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.project = self.dir / "song.mvproj.yaml"
        self.project.write_text(PROJECT, encoding="utf-8")

    def fail_replace(self):
        return patch("mviser.durable_io.os.replace", side_effect=OSError("publish failed"))

    def test_lyric_save_preserves_previous_yaml_on_publish_failure(self):
        before = self.project.read_bytes()
        doc = LyricDocument(self.project)
        doc.update(0, text="changed")
        with self.fail_replace(), self.assertRaisesRegex(OSError, "publish failed"):
            doc.save()
        self.assertEqual(self.project.read_bytes(), before)

    def test_project_settings_save_preserves_previous_yaml_on_publish_failure(self):
        before = self.project.read_bytes()
        doc = SettingsDocument(self.project, "project")
        doc.set(F["motion.pulse"], 0.25)
        with self.fail_replace(), self.assertRaisesRegex(OSError, "publish failed"):
            doc.save()
        self.assertEqual(self.project.read_bytes(), before)

    def test_global_settings_save_preserves_previous_yaml_on_publish_failure(self):
        path = self.dir / "global.yaml"
        path.write_text('style: {text_color: "#FFFFFF"}\n', encoding="utf-8")
        before = path.read_bytes()
        doc = SettingsDocument(path, "global")
        doc.set(F["project.fps"], 24)
        with self.fail_replace(), self.assertRaisesRegex(OSError, "publish failed"):
            doc.save()
        self.assertEqual(path.read_bytes(), before)

    def test_plain_project_save_uses_same_atomic_publication(self):
        before = self.project.read_bytes()
        with self.fail_replace(), self.assertRaisesRegex(OSError, "publish failed"):
            save_project({"project": {"bpm": 100}}, self.project)
        self.assertEqual(self.project.read_bytes(), before)


class CorruptLoadTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "broken.yaml"
        self.path.write_text("project: [\n", encoding="utf-8")
        self.before = self.path.read_bytes()

    def test_lyric_document_reports_bounded_error_without_mutation(self):
        with self.assertRaises(LyricEditError):
            LyricDocument(self.path)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_settings_document_reports_bounded_error_without_mutation(self):
        with self.assertRaises(SettingsError):
            SettingsDocument(self.path, "project")
        self.assertEqual(self.path.read_bytes(), self.before)


if __name__ == "__main__":
    unittest.main()
