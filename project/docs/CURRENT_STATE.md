# Current State

Last verified: 2026-09-27 — MVP-0 (MViser#2) implemented on branch `claude/mviser-issue-1-2-7mxifc`; `knt doctor` / `knt verify` green locally (Linux, pwsh 7.4)

## Implemented

- Repository Base 0.5.9 adopted (profile `cli`; CLI Default OVERRIDE, ci-test Default DISABLED).
- MVP-0 pipeline: YAML → compile (measure:beat → frame) → SceneState → Pillow render → FFmpeg MP4 with audio / PNG sequence.
- Chord symbol parser (major, minor, dim, dim7, aug, sus2, sus4, 6, 7, maj7, m7, m7b5, slash bass, tensions).
- Harmony layer (ADR 0002): `ChordSpec` in cents; mappers `symbol` / `degree` / `tones` (microtonal, JI, EDO) /
  `pitch_set`; analyzers `pitch_classes` / `identify` (fail-open UNKNOWN) / `function` (roman, diatonic, function);
  `project.key`, `harmony.display` (symbol / source / roman); μChordbot `.mcb` import.
- Motion presets `cut` / `fade` / `slide`, beat-phase `pulse`, per-event override.
- Automatic per-root chord colours with explicit overrides.
- Lyric track (ruby parsed; base text only rendered).
- CLI: `inspect`, `frame`, `render` (range `--start/--end`, `--frames`, `--no-audio`).
- 47 unit / E2E tests covering all eight MViser#2 verification units and the harmony layer.

## MViser#2 MVP-0 acceptance

All nine checkboxes are satisfied by `project/tests/` (YAML load, measure/beat→frame, active chord, local progress,
SceneState-based background+label, enter animation, frame sequence, audio MP4, boundary tests).

## Known issues / constraints

- Lyrics require a CJK font; on systems without Noto CJK / Yu Gothic / Meiryo set `style.font_path`.
- Fixed BPM, 4/4, single audio file; WAV duration auto-detected, other formats need `project.duration`.
- Ruby / vertical text are not rendered yet.
- KiNoTch. Runtime not integrated (see ADR 0001).
- Function analysis is a first cut (no key detection, secondary dominants reported as chromatic).
- "Music-dsl" repository not found; μChordbot DSL spec used as reference.

## Next work

1. KiNoTch. review of the rendered sample look (colours, font sizes, motion feel).
2. MVP-1: MIDI source (`imports: format: midi`) → `pitch_set` events; the identify analyzer already provides
   candidate / UNKNOWN resolution.
3. Analysis-driven styling (e.g. colour or motion by `function`).
4. Then #1 Priority A/B items (ruby rendering, subtitle sets, GUI preview).

## Verification

```text
knt.cmd doctor
knt.cmd setup
knt.cmd verify
python project/tools/make_click_wav.py project/samples/click.wav 135 16
python project/tools/run_mviser.py render project/samples/sample.mvproj.yaml -o project/output/sample.mp4
```
