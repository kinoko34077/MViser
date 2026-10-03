# Current State

Last verified: 2026-10-03 — accepted main `39680485d437cb278a4e117e87ce1ac28a9bb06b` includes
MViser#50 subtitle-set frame-output containment and MViser#51 lossless/fail-closed handoff serialization.
Post-main Verify `37116551150` and MViser audit `37116551140` are SUCCESS. Version 0.2.0.
#49 remains an explicit path-authority contract choice; #41/#42/#45 remain unresolved owner-visible Windows/AviUtl boundaries.

## Implemented (by area)

**Base / tooling**
- KiNoTch. Repository Base 0.5.9 (profile `cli`; CLI Default OVERRIDE, ci-test Default DISABLED). Runtime not used (ADR 0001).
- Dependencies per ADR 0003: Pillow, PyYAML, imageio-ffmpeg, mido, numpy, sounddevice, ruamel.yaml; tkinter for the GUI.

**Persistence**
- Project YAML, lyric-editor, and Project / Global Settings saves use same-directory staged writes, staged-file fsync, and atomic replacement (#40); pre-publication failures preserve the prior accepted file.
- Corrupt YAML opened through lyric/settings editing surfaces as a bounded domain error without recovery overwrite.

**Input / harmony**
- `.mvproj.yaml` schema v1; unquoted `M:B` positions read correctly (YAML base-60 disabled) (#25).
- Chord mappers `symbol` / `degree` / `tones` (microtonal, JI, EDO) / `pitch_set`; analyzers `pitch_classes` /
  `identify` (fail-open UNKNOWN) / `function` (ADR 0002).
- Imports: μChordbot `.mcb`, MIDI via `mido` (chord segmentation, single notes) (#2).

**Rendering**
- Frame compile → SceneState → Pillow; motion `cut` / `fade` / `slide`, beat pulse (#2); style rules by harmony (#4).
- Lyrics: ruby, vertical text, `follow` defaults, subtitle sets, repeated side text (#6, #27, #8, #19); CJK font discovery.

**Output**
- MP4 with audio, PNG sequence, range export (#2); alpha layers: RGBA PNG / ProRes 4444 / WebM, split layers (#23).
- Multi-subtitle-set frame export validates subtitle names as collision-safe single filesystem leaves and resolve-checks each output directory below the selected `--frames` root (#50).
- Editor handoff: AviUtl `.exo` + After Effects `.jsx` from editable templates (#29; exedit keys unverified); JSX title strings use JSON/JavaScript escaping and EXO CP932 publication fails closed instead of replacing unrepresentable path/text characters (#51).

**GUI** (ADR 0004)
- Preview, timeline (chords / lyrics / waveform / beat grid), audio-synced playback with silent fallback (#10, #12, #18).
- Settings window with Global / Project layers (#16); recent files, chord-colour toggle, guides (#20);
  time modes, project info (#27); light / dark theme, remembered prefs (#31).
- Subtitle editor (window and docked side panel), chord list, undo / redo (#25, #33, #35).

**CLI**: `inspect`, `frame`, `render` (`--start/--end`, `--frames`, `--layers`, `--split-layers`, `--format`,
`--subtitle-set`, `--all-subtitle-sets`, `--no-audio`), `handoff`, `gui`.

**Tests**: unit / E2E suite includes deterministic YAML persistence failure-injection coverage (#40), FFmpeg round trips and headless GUI models.

## Issue map

| Issue | State |
| --- | --- |
| #1 concept baseline | all items implemented (status table on #1); kept open as the long-term reference |
| #2 MVP-0 / MVP-1 | done |
| #4 #6 #8 #10 #12 #16 #18 #19 #20 #23 #25 #27 #31 #33 #35 | done (closed by their PRs) |
| #29 editor handoff | done (closed by PR #30); exedit keys are confirmed via #14 `handoff` |
| #14 manual verification | open — 12 of 16 automated; gui-audio ok (owner 2026-09-28); handoff ng → #42; midi-fl / aviutl-ae deferred (frozen, owner checks later) |
| #41 GUI playback jump with real audio (Windows) | guard + trace added; root cause waits on the local-run request (#45) |
| #45 local check request (Codex etc.) | open — tasks for #41 / #42 on the owner's Windows PC |
| #42 AviUtl cannot read .mov handoff | owner chose L-SMASH Works + .mov default (avi-rgba kept as option); re-check requested in #45 |
| #38 automated audit | `mviser audit` + workflow *MViser audit* (ADR 0005, `REVIEW_PROTOCOL.md`) |
| #40 durable YAML persistence | done — shared staged/fsync/atomic replacement path with deterministic failure-injection tests |
| #49 project asset path authority | open — explicit contained-only vs authorized-external contract choice required before implementation |
| #50 subtitle-set frame output containment | done in accepted implementation — unsafe/colliding output names fail closed before frame publication |
| #51 handoff serialization | done in accepted implementation — JSX title escaping is lossless and CP932-incompatible EXO references fail as HandoffError; physical #42/#45 gate remains separate |

## Known issues / constraints

- Machine-verified by `mviser audit` (Linux Xvfb + Windows CI): fonts/ruby, A/V sync, exports, alpha, GUI behaviour. Still human-only: audible output, running .exo/.jsx inside AviUtl/AE, a real FL Studio MIDI export (MViser#14).
- Fixed BPM, 4/4, single audio file; WAV duration auto-detected, other formats need `project.duration`.
- Vertical text: no rotation of long-vowel marks / punctuation, no tate-chu-yoko.
- Function analysis is a first cut (no key detection; secondary dominants reported as chromatic).
- Theme change recolours menus only after restart (Tk).
- The build container's default Python lacks tkinter; GUI smoke tests use system Python 3.12 + Xvfb.
- "Music-dsl" repository not found; μChordbot DSL spec used as reference.

## Manual verification

Canonical list: `project/verification/manual_checks.yaml` (`python project/tools/manual_check.py [--prepare|--markdown]`),
generated into MViser#14. Each check carries `automated_by` (and `boundary` if a human part remains);
#14 lists only the residual boundaries. Automated audit: `python project/tools/run_mviser.py audit` — see `REVIEW_PROTOCOL.md`.

## Next work

1. Collect MViser#14 results; fix templates / defaults accordingly (a failed `handoff` check reopens work on #29).
2. Tune MIDI `window` / `min_duration` with real FL Studio exports.
3. Candidates: chord editing in the GUI, advanced animation, variable tempo / time signatures.
