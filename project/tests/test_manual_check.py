import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
import manual_check


class ManualCheckTests(unittest.TestCase):
    def test_canonical_file_is_valid_and_renders(self):
        data = manual_check.load()
        md = manual_check.to_markdown(data)
        for check in data["checks"]:
            self.assertIn(f"**{check['id']}**", md)
        self.assertIn("manual_checks.yaml", md)
        self.assertIn("### Priority (please check these first)", md)
        self.assertLess(md.index("**handoff** —"), md.index("### All checks"))

    def test_status_marks_and_validation(self):
        data = {"checks": [
            {"id": "a", "area": "x", "steps": ["do"], "expected": "e", "status": "ok"},
            {"id": "b", "area": "x", "steps": ["python x"], "expected": "e", "status": "ng", "result": "broken"},
        ]}
        md = manual_check.to_markdown(data)
        self.assertIn("- [x] **a**", md)
        self.assertIn("- [ ] **b** (x, from -) **NG**", md)
        self.assertIn("Result: broken", md)
        bad = Path(tempfile.mkdtemp()) / "c.yaml"
        bad.write_text("checks: [{id: a, area: x, steps: [], expected: e, status: done}]", encoding="utf-8")
        with self.assertRaises(ValueError):
            manual_check.load(bad)


if __name__ == "__main__":
    unittest.main()
