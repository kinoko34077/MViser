"""Preset motions as pure functions of event-local time (MVP-0)."""

from __future__ import annotations

from dataclasses import dataclass

PRESETS = ("cut", "fade", "slide")


@dataclass(frozen=True)
class MotionState:
    opacity: float = 1.0
    offset_x: float = 0.0  # fraction of frame width
    offset_y: float = 0.0  # fraction of frame height
    scale: float = 1.0


def _ease_out(p: float) -> float:
    return 1.0 - (1.0 - p) ** 3


def enter(preset: str, local_seconds: float, duration: float) -> MotionState:
    if preset not in PRESETS:
        raise ValueError(f"unknown motion preset: {preset!r} (expected one of {PRESETS})")
    if preset == "cut" or duration <= 0 or local_seconds >= duration:
        return MotionState()
    p = _ease_out(min(max(local_seconds / duration, 0.0), 1.0))
    if preset == "fade":
        return MotionState(opacity=p)
    return MotionState(opacity=p, offset_x=(1.0 - p) * 0.08)


def pulse(beat_phase: float, amount: float) -> float:
    """Scale factor peaking on each beat head and decaying through the beat."""
    if amount <= 0:
        return 1.0
    return 1.0 + amount * (1.0 - beat_phase) ** 3
