"""SceneState resolution: frame -> everything the renderer needs, no drawing."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

from .chord_engine import Chord
from .motion import MotionState, enter, pulse
from .project_data import CompiledProject


@dataclass(frozen=True)
class SceneState:
    frame: int
    time: float
    background_color: str
    text_color: str
    beat_phase: float
    chord_label: str | None = None
    chord_progress: float = 0.0
    chord_motion: MotionState = MotionState()
    chord_scale: float = 1.0
    lyric: str | None = None
    lyric_motion: MotionState = MotionState()


def auto_chord_color(chord: Chord) -> str:
    """Deterministic colour: hue from root pitch class, darker for minor-ish."""
    hue = chord.root_pc / 12.0
    lightness = 0.30 if chord.is_minor else 0.42
    r, g, b = colorsys.hls_to_rgb(hue, lightness, 0.55)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def chord_background(project: CompiledProject, payload: dict) -> str:
    style = project.doc["style"]
    chord: Chord = payload["chord"]
    if "color" in payload:
        return payload["color"]
    colors = style["chord_colors"]
    for key in (chord.raw_symbol, chord.root + ({"minor": "m"}.get(chord.quality, "")), chord.root):
        if key in colors:
            return colors[key]
    if style.get("auto_chord_colors", True):
        return auto_chord_color(chord)
    return style["background_color"]


def resolve_scene_state(project: CompiledProject, frame: int) -> SceneState:
    tempo = project.tempo
    style = project.doc["style"]
    motion = project.doc["motion"]
    t = tempo.frame_to_seconds(frame)
    phase = tempo.beat_phase(t)
    state = dict(
        frame=frame,
        time=t,
        background_color=style["background_color"],
        text_color=style["text_color"],
        beat_phase=phase,
    )

    chord_event = project.tracks["chord"].active(frame)
    if chord_event:
        payload = chord_event.payload
        local = tempo.frame_to_seconds(chord_event.local_frame(frame))
        state.update(
            background_color=chord_background(project, payload),
            chord_label=payload.get("label", payload["value"]),
            chord_progress=chord_event.progress(frame),
            chord_motion=enter(payload.get("motion", motion["enter"]), local, float(motion["enter_duration"])),
            chord_scale=pulse(phase, float(motion["pulse"])),
        )

    lyric_event = project.tracks["lyric"].active(frame)
    if lyric_event:
        payload = lyric_event.payload
        local = tempo.frame_to_seconds(lyric_event.local_frame(frame))
        state.update(
            lyric=payload["text"],
            lyric_motion=enter(payload.get("motion", motion["enter"]), local, float(motion["enter_duration"])),
        )
    return SceneState(**state)
