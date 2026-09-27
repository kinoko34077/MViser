# ADR 0005: Automated audit replaces human re-checks

- Status: accepted
- Issue: MViser#38 (follows kinotch-repo-monitor#29)

## Context
Checks in `project/verification/manual_checks.yaml` (#14) waited on a human to open the GUI, look at
frames and compare timings. Most of them are machine-verifiable: pixel/glyph inspection, FFmpeg decoding,
onset detection, widget state of the real Tk app.

## Decision
- `python project/tools/run_mviser.py audit` (package `mviser.audit`) runs every check against real
  outputs and prints `PASS/WARN/FAIL`, writing `audit_report.json`, `audit_summary.md` and evidence files.
- Conclusion is `PASS` / `PASS WITH NON-BLOCKING BOUNDARY` / `FAIL — follow-up required`.
  A crashing check is FAIL with its traceback. WARN is used only for a named boundary the machine cannot
  cross (audio device, running inside AviUtl/AE, a real FL export).
- GUI checks drive the real `PreviewApp` (Xvfb on Linux). `--gui auto` → WARN without a display;
  CI uses `--gui on` so a missing display is a FAIL.
- A project-owned workflow `.github/workflows/mviser-audit.yml` (Ubuntu + Windows) uploads the reports.
  The Base `verify.yml` stays untouched.
- Each manual check carries `automated_by` (and `boundary` when a residual remains); #14 lists only residuals.
- Defects the audit finds get their own issue; checks are not weakened to pass.

## Consequences
Reviews quote the report (see `project/docs/REVIEW_PROTOCOL.md`) instead of asking for screenshots.
Audio audibility, AviUtl/AE execution and real FL exports remain human boundaries.
