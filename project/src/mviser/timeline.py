"""Time resolution: musical positions -> seconds -> frames, event ranges.

MVP-0 fixes BPM, 4/4 and FPS. Rendering never sees measures or beats; they are
compiled to frames here.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import Any

BEATS_PER_MEASURE = 4

_POSITION_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+(?:\.\d+)?)\s*$")


class TimelineError(ValueError):
    pass


@dataclass(frozen=True)
class Tempo:
    bpm: float
    fps: int
    offset: float = 0.0

    def __post_init__(self):
        if self.bpm <= 0:
            raise TimelineError("bpm must be positive")
        if self.fps <= 0:
            raise TimelineError("fps must be positive")

    @property
    def beat_sec(self) -> float:
        return 60.0 / self.bpm

    def position_to_seconds(self, measure: int, beat: float) -> float:
        if measure < 1 or beat < 1:
            raise TimelineError(f"measure/beat are 1-based: {measure}:{beat}")
        return self.offset + ((measure - 1) * BEATS_PER_MEASURE + (beat - 1)) * self.beat_sec

    def to_seconds(self, at: Any) -> float:
        """Accept seconds (number), ``"M:B"`` strings or ``{measure, beat}`` maps."""
        if isinstance(at, bool):
            raise TimelineError(f"invalid time: {at!r}")
        if isinstance(at, (int, float)):
            if at < 0:
                raise TimelineError(f"negative time: {at}")
            return float(at)
        if isinstance(at, dict):
            return self.position_to_seconds(int(at["measure"]), float(at.get("beat", 1)))
        if isinstance(at, str):
            m = _POSITION_RE.match(at)
            if m:
                return self.position_to_seconds(int(m.group(1)), float(m.group(2)))
            try:
                return self.to_seconds(float(at))
            except ValueError:
                pass
        raise TimelineError(f"invalid time: {at!r}")

    def seconds_to_frame(self, seconds: float) -> int:
        return int(round(seconds * self.fps))

    def frame_to_seconds(self, frame: int) -> float:
        return frame / self.fps

    def beat_position(self, seconds: float) -> float:
        return (seconds - self.offset) / self.beat_sec

    def beat_phase(self, seconds: float) -> float:
        return self.beat_position(seconds) % 1.0


@dataclass(frozen=True)
class Event:
    start_frame: int
    end_frame: int  # exclusive
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def contains(self, frame: int) -> bool:
        return self.start_frame <= frame < self.end_frame

    def local_frame(self, frame: int) -> int:
        return frame - self.start_frame

    def progress(self, frame: int) -> float:
        """0..1 progress across the event's own range."""
        length = self.end_frame - self.start_frame
        if length <= 0:
            return 1.0
        return min(max((frame - self.start_frame) / length, 0.0), 1.0)


class Track:
    """Non-overlapping events of one type; each lasts until the next one starts."""

    def __init__(self, events: list[Event]):
        self.events = sorted(events, key=lambda e: e.start_frame)
        self._starts = [e.start_frame for e in self.events]

    def active(self, frame: int) -> Event | None:
        i = bisect.bisect_right(self._starts, frame) - 1
        if i < 0:
            return None
        event = self.events[i]
        return event if event.contains(frame) else None


def build_track(event_type: str, starts: list[tuple[int, dict[str, Any]]], end_frame: int) -> Track:
    """Create a Track from (start_frame, payload) pairs.

    Events at the same frame: the later-declared one wins, earlier ones get an
    empty range. Payloads may carry ``duration_frames`` to end before the next.
    """
    ordered = sorted(enumerate(starts), key=lambda item: (item[1][0], item[0]))
    events: list[Event] = []
    for i, (_, (start, payload)) in enumerate(ordered):
        nxt = ordered[i + 1][1][0] if i + 1 < len(ordered) else end_frame
        end = max(start, min(nxt, end_frame))
        duration = payload.get("duration_frames")
        if duration is not None:
            end = min(end, start + int(duration))
        events.append(Event(start, end, event_type, payload))
    return Track(events)
