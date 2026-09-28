"""Manual verification helper.

  python project/tools/manual_check.py            # list checks and status
  python project/tools/manual_check.py --prepare  # create sample assets (click.wav, sample.mid)
  python project/tools/manual_check.py --markdown # Issue body generated from manual_checks.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[1]
CHECKS = PROJECT / "verification" / "manual_checks.yaml"
STATUS_MARK = {"ok": "x", "ng": " ", "pending": " ", "skip": "x", "deferred": " "}
STATUSES = tuple(STATUS_MARK)


def load(path: Path = CHECKS) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    ids = set()
    for check in data["checks"]:
        for key in ("id", "area", "steps", "expected", "status"):
            if key not in check:
                raise ValueError(f"check {check.get('id', '?')}: missing {key}")
        if check.get("priority", "normal") not in ("high", "normal"):
            raise ValueError(f"check {check['id']}: priority must be high or normal")
        if check["status"] not in STATUSES:
            raise ValueError(f"check {check['id']}: status must be one of {STATUSES}")
        if check["id"] in ids:
            raise ValueError(f"duplicate check id {check['id']}")
        ids.add(check["id"])
    return data


def to_markdown(data: dict) -> str:
    lines = [
        "## Manual verification (real hardware)",
        "",
        "Generated from `project/verification/manual_checks.yaml` — edit that file and regenerate with",
        "`python project/tools/manual_check.py --markdown`; this body is replaceable output.",
        "",
        f"Environment: {data.get('environment_hint', '')}",
        "",
    ]
    auto = [c for c in data["checks"] if c.get("automated_by") and not c.get("boundary")]
    if auto:
        lines += ["### Automated (no human action needed)", "",
                  "Reproduced by `python project/tools/run_mviser.py audit` (CI: MViser audit workflow, JSON report "
                  "artifact); see `project/docs/REVIEW_PROTOCOL.md`.", ""]
        lines += [f"- **{c['id']}** — `{c['automated_by']}`" for c in auto]
        lines.append("")
    residual = [c for c in data["checks"] if c not in auto]
    data = {**data, "checks": residual}
    if auto:
        lines += ["### Residual boundaries (human check still required)", ""]
    high = [c for c in data["checks"] if c.get("priority") == "high" and c["status"] in ("pending", "ng")]
    if high:
        lines += ["### Priority (please check these first)", ""]
        lines += [f"- **{c['id']}** — {c['expected'].split(';')[0]}" for c in high]
        lines += ["", "### All checks", ""]
    for c in data["checks"]:
        tag = {"ng": " **NG**", "skip": " (skipped)", "deferred": " (deferred — frozen until the owner checks)"}.get(c["status"], "")
        lines.append(f"- [{STATUS_MARK[c['status']]}] **{c['id']}** ({c['area']}, from {c.get('from', '-')}){tag}")
        for step in c["steps"]:
            lines.append(f"  - `{step}`" if step.startswith("python") else f"  - {step}")
        lines.append(f"  - Expected: {c['expected']}")
        if c.get("boundary"):
            lines.append(f"  - Only this remains for a human: {c['boundary']} (rest: `{c['automated_by']}`)")
        if c.get("result"):
            lines.append(f"  - Result: {c['result']}")
    lines += ["", "Report results as a comment (id + ok/ng + notes); the agent updates the YAML and this body."]
    return "\n".join(lines)


def prepare() -> list[Path]:
    sys.path.insert(0, str(PROJECT / "tools"))
    from make_click_wav import make_click_wav

    samples = PROJECT / "samples"
    wav = samples / "click.wav"
    make_click_wav(wav, 135, 16)
    created = [wav]
    try:
        import mido

        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(135))])
        for notes in ([52, 55, 59], [48, 52, 55], [50, 54, 57], [47, 50, 54, 57]):  # Em C D Bm7
            for n in notes:
                track.append(mido.Message("note_on", note=n, velocity=90, time=0))
            for i, n in enumerate(notes):
                track.append(mido.Message("note_off", note=n, velocity=0, time=480 * 8 if i == 0 else 0))
        mid.tracks.append(track)
        path = samples / "sample.mid"
        mid.save(str(path))
        created.append(path)
    except ImportError:
        pass
    return created


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args(argv)
    data = load()
    if args.prepare:
        for path in prepare():
            print(f"created {path}")
    if args.markdown:
        print(to_markdown(data))
    elif not args.prepare:
        for c in data["checks"]:
            print(f"{c['status']:8} {c['id']:12} {c['expected']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
