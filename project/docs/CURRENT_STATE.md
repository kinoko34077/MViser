# Current State

Last verified: 2026-09-27 — main 3685c24 green; ruby / vertical lyrics (MViser#6) in PR

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
- CLI: `inspect`, `frame`, `render` (range `--start/--end`, `--frames`, `--no-audio`).
- 67 unit / E2E tests covering all eight MViser#2 verification units, the harmony layer, MIDI import, style rules and lyric layout.

## MViser#2 MVP-0 / MVP-1 acceptance

MVP-0 and MVP-1 are satisfied (recorded on MViser#2). MVP-0's nine checkboxes are covered by `project/tests/` (YAML load, measure/beat→frame, active chord, local progress,
SceneState-based background+label, enter animation, frame sequence, audio MP4, boundary tests).

## Known issues / constraints

- Lyrics require a CJK font; on systems without Noto CJK / Yu Gothic / Meiryo set `style.font_path`.
- Fixed BPM, 4/4, single audio file; WAV duration auto-detected, other formats need `project.duration`.
- Vertical text: no rotation of long-vowel marks / punctuation, no tate-chu-yoko.
- KiNoTch. Runtime not integrated (see ADR 0001).
- Function analysis is a first cut (no key detection, secondary dominants reported as chromatic).
- "Music-dsl" repository not found; μChordbot DSL spec used as reference.

## Next work

1. KiNoTch. review of the rendered sample look (colours, font sizes, motion feel).
2. Try MIDI import with real FL Studio exports; tune `window` / `min_duration` defaults.
3. Then #1 Priority A/B items (multiple subtitle sets, GUI preview).

## Verification

```text
knt.cmd doctor
knt.cmd setup
knt.cmd verify
python project/tools/make_click_wav.py project/samples/click.wav 135 16
python project/tools/run_mviser.py render project/samples/sample.mvproj.yaml -o project/output/sample.mp4
```
