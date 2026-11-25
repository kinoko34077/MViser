"""project.yaml の数値設定で nan/inf が描画時の生例外にならず、読込時に ProjectError になること。"""
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from mviser.project_data import ProjectError, load_project

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "sample.mvproj.yaml"


class NumericValidationTests(unittest.TestCase):
    def load(self, old, new):
        text = SAMPLE.read_text(encoding="utf-8")
        self.assertIn(old, text)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.mvproj.yaml"
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            return load_project(path, global_doc={})

    def test_sample_still_loads(self):
        self.assertGreater(self.load("pulse: 0.04", "pulse: 0.04").total_frames, 1)

    def test_non_finite_or_invalid_numbers_are_project_errors(self):
        cases = (
            ("chord_font_size: 160", "chord_font_size: .inf"),
            ("chord_font_size: 160", "chord_font_size: .nan"),
            ("chord_font_size: 160", "chord_font_size: -5"),
            ("chord_font_size: 160", "chord_font_size: 0"),
            ("lyric_font_size: 56", "lyric_font_size: .nan"),
            ("pulse: 0.04", "pulse: .nan"),
            ("pulse: 0.04", "pulse: .inf"),
            ("pulse: 0.04", "pulse: -1"),
            ("enter_duration: 0.2", "enter_duration: .nan"),
            ("start: 0.0", "start: .nan"),
            ("start: 0.0", "start: .inf"),
            ("start: 0.0", "start: -1"),
            ("scroll: 30", "scroll: .inf"),
            ("scroll: 30", "scroll: .nan"),
        )
        for old, new in cases:
            with self.subTest(new=new), self.assertRaises(ProjectError):
                self.load(old, new)

    def test_non_finite_rule_and_event_pulse_are_project_errors(self):
        for old, new in (("pulse: 0.08", "pulse: .nan"), ("pulse: 0.08", "pulse: .inf")):
            with self.subTest(new=new), self.assertRaises(ProjectError):
                self.load(old, new)


if __name__ == "__main__":
    unittest.main()
