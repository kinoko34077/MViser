# Current State

Last verified: 2026-09-27 — main c11a275 green; integrated panels (MViser#33) in PR

## Implemented

- Repository Base 0.5.9 adopted (profile `cli`; CLI Default OVERRIDE, ci-test Default DISABLED).
- MVP-0 pipeline: YAML → compile (measure:beat → frame) → SceneState → Pillow render → FFmpeg MP4 with audio / PNG sequence.
- Chord symbol parser (major, minor, dim, dim7, aug, sus2, sus4, 6, 7, maj7, m7, m7b5, slash bass, tensions).
- Harmony layer (ADR 0002): `ChordSpec` in cents; mappers `symbol` / `degree` / `tones` (microtonal, JI, EDO) /
  `pitch_set`; analyzers `pitch_classes` / `identify` (fail-open UNKNOWN) / `function` (roman, diatonic, function);
  `project.key`, `harmony.display` (symbol / source / roman); μChordbot `.mcb` import.
- Analysis-driven styling `style.rules` (MViser#4): colour / text colour / motion / pulse by quality, function, roman, diatonic, microtonal, notation, root.
- MVP-1 MIDI import (`mido`): chord segmentation (strum window, silence gaps) and single-note mode (ADR 0003).
- Motion presets `cut` / `fade` / `slide`, beat-phase `pulse`, per-event override.
- Automatic per-root chord colours with explicit overrides.
- Lyric track with ruby rendering (align center/left/right, scale) and vertical text; per-event position (MViser#6).
- Multiple subtitle sets with per-set lyric style; `--subtitle-set`, `--all-subtitle-sets` (MViser#8).
- Preview GUI (tkinter): seek, timeline, playback with synced audio (sounddevice, silent fallback, mute), auto-reload, export, subtitle set switch (MViser#10).
- Integrated side panel (docked subtitle editor + chord list), toggle and width remembered (MViser#33).
- Dark theme; GUI preferences (theme, time mode, guides, chord colours) remembered (MViser#31).
- Editor handoff: split alpha layers + AviUtl .exo + AE .jsx from editable templates (MViser#29; exedit keys unverified).
- `follow` for lyric vertical / ruby_align / position; GUI time display modes; Help → Project info (MViser#27).
- Subtitle editor window (add / retime / edit / delete at the playhead) (MViser#25).
- Loader reads unquoted `M:B` positions correctly (YAML base-60 disabled).
- Compositing output: layer selection, RGBA PNG, ProRes 4444 / WebM with alpha, split layers (MViser#23).
- GUI: recent files, preview-only chord colour toggle, guideline overlay (MViser#20).
- Repeated side text in the margins, scrolling per lyric event (MViser#19).
- Timeline waveform row and beat / measure grid (MViser#18).
- Global / Project settings layers and settings window with override toggles (MViser#16).
- CJK font discovery (Windows / macOS / Linux IPA, Noto, WenQuanYi, fontconfig).
- CLI: `inspect`, `frame`, `render`, `gui` (range `--start/--end`, `--frames`, `--no-audio`, `--subtitle-set`, `--all-subtitle-sets`).
- 143 unit / E2E tests covering all eight MViser#2 verification units, the harmony layer, MIDI import, style rules, lyric layout, subtitle sets, the preview controller and the audio player.

## MViser#2 MVP-0 / MVP-1 acceptance

MVP-0 and MVP-1 are satisfied (recorded on MViser#2). MVP-0's nine checkboxes are covered by `project/tests/` (YAML load, measure/beat→frame, active chord, local progress,
SceneState-based background+label, enter animation, frame sequence, audio MP4, boundary tests).

## Known issues / constraints

- Lyrics need a CJK font; auto-discovered on Windows / macOS / common Linux fonts, otherwise set `style.font_path`.
- Audio playback not verified on real hardware in the build container (no PortAudio there; fallback path verified); the Linux Python used in the build container lacks tkinter (GUI smoke run with system Python 3.12 + Xvfb).
- Fixed BPM, 4/4, single audio file; WAV duration auto-detected, other formats need `project.duration`.
- Vertical text: no rotation of long-vowel marks / punctuation, no tate-chu-yoko.
- KiNoTch. Runtime not integrated (see ADR 0001).
- Function analysis is a first cut (no key detection, secondary dominants reported as chromatic).
- "Music-dsl" repository not found; μChordbot DSL spec used as reference.

## Manual verification

Real-hardware checks are tracked in MViser#14; the canonical list is `project/verification/manual_checks.yaml`
(`python project/tools/manual_check.py [--prepare|--markdown]`).

## Next work

1. KiNoTch. review of the rendered sample look (colours, font sizes, motion feel).
2. Try MIDI import with real FL Studio exports; tune `window` / `min_duration` defaults.
3. #1 baseline items are all implemented; tune everything from MViser#14 feedback, then consider undo/redo and chord editing in the GUI.

## Verification

```text
knt.cmd doctor
knt.cmd setup
knt.cmd verify
python project/tools/make_click_wav.py project/samples/click.wav 135 16
python project/tools/run_mviser.py render project/samples/sample.mvproj.yaml -o project/output/sample.mp4
```
