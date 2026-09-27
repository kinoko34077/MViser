# 0002 Harmony mapper / analyzer layer

Date: 2026-09-27 — Status: accepted

## Context

KiNoTch. asked for chord specification and analysis to pass through a mapping layer so chord handling can be
extended later. References reviewed:

- **μChordbot** (`Micro-Chordbot`): pitches in microSteps (1 cent = 100), chords as root + root-relative `tones[]`
  (`localCent` or PitchPreset `cent`, `octaveShift`), progression parts with `beats`; DSL degree presets (P1, b2…).
- **microtone-piano**: pitch definitions typed as `edo` / `cents` / `ratio` / `frequency` resolved by one function.
- A separate "Music-dsl" repository was not found among the accessible repositories; μChordbot's DSL spec
  (`docs/specs/dsl/01_dsl_spec.md`) was used as the DSL reference instead.

## Decision

1. One notation-neutral type, `ChordSpec`, with **cents** as the pitch unit (root, tones, bass). This covers 12-TET,
   EDO, JI ratios and free cents the same way the two reference apps do.
2. **Mapper** protocol (`name`, `accepts(value)`, `map(value, context) -> ChordSpec`) per notation:
   `symbol`, `degree`, `tones`, `pitch_set`. Auto-detection tries mappers in registration order.
3. **Analyzer** protocol (`name`, `analyze(spec, context) -> ChordSpec`) chained in the order given by
   `harmony.analyzers`: `pitch_classes`, `identify` (template match, fail-open UNKNOWN), `function` (roman/function).
4. **Sources** (`imports:`) convert external files into ordinary events that then pass through mappers:
   first `mcb` (μChordbot project).
5. `HarmonyRegistry` is the only entry point used by `project_data`; scene/render depend on `ChordSpec` only.

## Consequences

- MVP-1 MIDI input = a new source (MIDI → `pitch_set` events); no downstream change.
- New analyses (tension, voice-leading, key detection) are new Analyzers; colours/motions may read `spec.analysis`.
- `chord_engine.parse_chord` remains as the symbol mapper's parser; other code should not import it directly.
- Not a Runtime Contract candidate: the meaning is MViser-domain specific (see ADR 0001).
