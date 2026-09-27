"""SceneState resolution: frame -> everything the renderer needs, no drawing."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

from .harmony import ChordSpec
from .harmony.qualities import MINOR_LIKE
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


def is_minor_like(spec: ChordSpec) -> bool:
    quality = spec.quality or spec.analysis.get("identified", {}).get("quality")
    return quality in MINOR_LIKE


def auto_chord_color(spec: ChordSpec) -> str:
    """Deterministic colour: hue from root cents (microtonal roots get in-between hues),
    darker for minor-like qualities."""
    hue = (spec.root_cents % 1200) / 1200.0
    lightness = 0.30 if is_minor_like(spec) else 0.42
    r, g, b = colorsys.hls_to_rgb(hue, lightness, 0.55)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def chord_background(project: CompiledProject, payload: dict) -> str:
    style = project.doc["style"]
    spec: ChordSpec = payload["chord"]
    if "color" in payload:
        return payload["color"]
    colors = style["chord_colors"]
    raw = payload["value"] if isinstance(payload["value"], str) else None
    keys = [raw, spec.display, spec.root_name + ("m" if is_minor_like(spec) else ""), spec.root_name]
    if "roman" in spec.analysis:
        keys.insert(2, spec.analysis["roman"])
    for key in keys:
        if key in colors:
            return colors[key]
    if "background_color" in payload.get("rule_style", {}):
        return payload["rule_style"]["background_color"]
    if style.get("auto_chord_colors", True):
        return auto_chord_color(spec)
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
        rule = payload.get("rule_style", {})
        preset = payload.get("motion", rule.get("motion", motion["enter"]))
        amount = payload.get("pulse", rule.get("pulse", motion["pulse"]))
        state.update(
            background_color=chord_background(project, payload),
            text_color=rule.get("text_color", style["text_color"]),
            chord_label=payload.get("label", payload["display"]),
            chord_progress=chord_event.progress(frame),
            chord_motion=enter(preset, local, float(motion["enter_duration"])),
            chord_scale=pulse(phase, float(amount)),
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
