import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml

import _path  # noqa: F401
from mviser.audit import CHECKS, AuditContext, CheckResult, run_audit
from mviser.audit.core import FAIL, PASS, WARN, check, conclusion
from mviser.audit.media import onsets

MANUAL = Path(__file__).resolve().parents[1] / "verification" / "manual_checks.yaml"


class AuditCoreTests(unittest.TestCase):
    def test_conclusion_wording(self):
        r = lambda s: CheckResult("x", s, "")  # noqa: E731
        self.assertEqual(conclusion([r(PASS)]), "PASS")
        self.assertEqual(conclusion([r(PASS), r(WARN)]), "PASS WITH NON-BLOCKING BOUNDARY")
        self.assertEqual(conclusion([r(WARN), r(FAIL)]), "FAIL — follow-up required")

    def test_crashing_check_is_fail_with_traceback_and_report_written(self):
        @check("zz-crash", "crash")
        def crash(ctx):
            raise RuntimeError("boom")

        try:
            out = Path(tempfile.mkdtemp())
            report = run_audit(AuditContext(out, gui="off"), only=["zz-crash"], echo=lambda *_: None)
            self.assertTrue(report["conclusion"].startswith("FAIL"))
            saved = json.loads((out / "audit_report.json").read_text(encoding="utf-8"))
            self.assertIn("boom", saved["checks"][0]["error"])
            self.assertIn("zz-crash", (out / "audit_summary.md").read_text(encoding="utf-8"))
        finally:
            CHECKS.pop("zz-crash")

    def test_unknown_id_rejected(self):
        with self.assertRaises(ValueError):
            run_audit(AuditContext(Path(tempfile.mkdtemp()), gui="off"), only=["nope"], echo=lambda *_: None)

    def test_gui_off_is_warn_with_boundary(self):
        report = run_audit(AuditContext(Path(tempfile.mkdtemp()), gui="off"), only=["gui-basic"], echo=lambda *_: None)
        self.assertEqual(report["checks"][0]["status"], WARN)
        self.assertTrue(report["checks"][0]["boundary"])

    def test_every_manual_check_is_mapped_to_an_audit_check(self):
        run_audit  # registry import side effect happens inside run_audit; import modules directly
        from mviser.audit import checks_gui, checks_input, checks_output, checks_render  # noqa: F401
        for c in yaml.safe_load(MANUAL.read_text(encoding="utf-8"))["checks"]:
            self.assertIn(c["id"], CHECKS)
            self.assertEqual(c["automated_by"], f"mviser audit --only {c['id']}")

    def test_onsets(self):
        rate = 1000
        sig = np.zeros(rate * 2, dtype=np.float32)
        sig[[100, 600, 1500]] = 1.0
        self.assertEqual([round(t, 2) for t in onsets(sig, rate)], [0.1, 0.6, 1.5])


if __name__ == "__main__":
    unittest.main()
