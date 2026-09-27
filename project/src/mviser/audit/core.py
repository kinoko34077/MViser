"""Audit registry, context and report."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
PROJECT = Path(__file__).resolve().parents[3]  # .../project


@dataclass
class CheckResult:
    id: str
    status: str
    summary: str
    values: dict[str, Any] = field(default_factory=dict)
    rule: str = ""
    boundary: str = ""
    artifacts: list[str] = field(default_factory=list)
    error: str = ""
    seconds: float = 0.0


@dataclass
class AuditContext:
    out: Path
    gui: str = "auto"            # auto | on | off
    work: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="mviser-audit-")))

    def artifact(self, name: str) -> Path:
        path = self.out / "artifacts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def rel(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.out.resolve()))
        except ValueError:
            return str(path)

    def sample(self) -> Path:
        """Private copy of the sample project + generated assets (never touches the repo samples)."""
        target = self.work / "sample"
        if not (target / "sample.mvproj.yaml").exists():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy(PROJECT / "samples" / "sample.mvproj.yaml", target / "sample.mvproj.yaml")
            sys.path.insert(0, str(PROJECT / "tools"))
            from make_click_wav import make_click_wav

            make_click_wav(target / "click.wav", 135, 16)
        return target / "sample.mvproj.yaml"


CheckFn = Callable[[AuditContext], CheckResult]
CHECKS: dict[str, tuple[str, CheckFn]] = {}


def check(check_id: str, title: str):
    def register(fn: CheckFn) -> CheckFn:
        CHECKS[check_id] = (title, fn)
        return fn
    return register


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _environment() -> dict[str, Any]:
    from ..render_engine import load_font
    from ..video import find_ffmpeg

    env: dict[str, Any] = {"platform": platform.platform(), "python": sys.version.split()[0]}
    try:
        ff = subprocess.run([find_ffmpeg(), "-version"], capture_output=True, text=True, timeout=20)
        env["ffmpeg"] = ff.stdout.splitlines()[0] if ff.stdout else "unknown"
    except Exception as exc:  # environment evidence only
        env["ffmpeg"] = f"unavailable: {exc}"
    env["font"] = getattr(load_font(None, 20), "path", "pillow-default")
    return env


def conclusion(results: list[CheckResult]) -> str:
    if any(r.status == FAIL for r in results):
        return "FAIL — follow-up required"
    if any(r.status == WARN for r in results):
        return "PASS WITH NON-BLOCKING BOUNDARY"
    return "PASS"


def run_audit(ctx: AuditContext, only: list[str] | None = None, echo=print) -> dict[str, Any]:
    from . import checks_gui, checks_input, checks_output, checks_render  # noqa: F401  (register checks)

    ctx.out.mkdir(parents=True, exist_ok=True)
    ids = [i for i in CHECKS if not only or i in only]
    unknown = sorted(set(only or []) - set(CHECKS))
    if unknown:
        raise ValueError(f"unknown check ids {unknown}; available: {sorted(CHECKS)}")
    results: list[CheckResult] = []
    for check_id in ids:
        title, fn = CHECKS[check_id]
        started = time.perf_counter()
        try:
            result = fn(ctx)
        except Exception as exc:  # a crashing check is a FAIL with evidence, never a silent skip
            result = CheckResult(check_id, FAIL, f"check crashed: {exc}", error=traceback.format_exc())
        result.seconds = round(time.perf_counter() - started, 2)
        results.append(result)
        echo(f"[{result.status:4}] {check_id:17} {result.summary}")
    report = {
        "tool": "mviser audit",
        "sha": _git_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": _environment(),
        "gui_mode": ctx.gui,
        "conclusion": conclusion(results),
        "counts": {s: sum(r.status == s for r in results) for s in (PASS, WARN, FAIL)},
        "checks": [asdict(r) for r in results],
    }
    (ctx.out / "audit_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ctx.out / "audit_summary.md").write_text(markdown_summary(report), encoding="utf-8")
    echo(f"conclusion: {report['conclusion']}  ({report['counts']})  report: {ctx.out / 'audit_report.json'}")
    return report


def markdown_summary(report: dict[str, Any]) -> str:
    lines = [f"## MViser audit — {report['conclusion']}", "",
             f"- SHA: `{report['sha']}`", f"- When: {report['timestamp']}",
             f"- Environment: {report['environment'].get('platform')} / Python {report['environment'].get('python')}"
             f" / {report['environment'].get('ffmpeg')} / font `{report['environment'].get('font')}`",
             f"- GUI mode: {report['gui_mode']}", "", "| check | result | summary | boundary |", "| --- | --- | --- | --- |"]
    for c in report["checks"]:
        lines.append(f"| {c['id']} | {c['status']} | {c['summary']} | {c['boundary'] or '-'} |")
    return "\n".join(lines) + "\n"
