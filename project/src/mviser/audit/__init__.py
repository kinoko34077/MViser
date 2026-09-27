"""Automated audit replacing human verification (MViser#38, after repo-monitor#29).

Each check measures real outputs (frames, decoded audio/video, FFmpeg probes, live Tk widgets, the OS audio
device) and returns PASS / WARN / FAIL with values, the rule used and artifact paths. WARN is used only for a
narrow boundary the machine cannot establish (e.g. no audio device, no display, AviUtl not available).
"""

from .core import CHECKS, AuditContext, CheckResult, run_audit

__all__ = ["CHECKS", "AuditContext", "CheckResult", "run_audit"]
