# 0003 Prefer established libraries; MIDI via mido

Date: 2026-09-27 — Status: accepted

## Decision

KiNoTch. policy: when a well-maintained library satisfies the requirement/spec, use it instead of writing our own.
Custom code is kept only where MViser-specific meaning lives (timeline→frame, SceneState, harmony mapper contracts).

Current dependencies: Pillow (drawing), PyYAML (project file), imageio-ffmpeg (FFmpeg binary), **mido** (MIDI).

MIDI reading uses `mido` (pure Python, tempo-map aware `merge_tracks`/`tick2second`). Alternatives:

| Library | Why not now |
| --- | --- |
| pretty_midi | adds numpy; its extra features (piano roll, synthesis) are not needed |
| music21 | very large; its chord naming would bypass the ADR 0002 mapper/analyzer contract. May be wrapped later as an optional **Analyzer** if deeper analysis is wanted |
| miditoolkit | less widely used; no advantage for note extraction |

Chord naming stays in the `identify` analyzer because it must handle cents/microtonal input and fail-open UNKNOWN,
which general libraries do not model.
