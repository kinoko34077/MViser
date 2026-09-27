# MViser Specification — MVP-0

Status: provisional (MViser#2 MVP-0). Long-term concept baseline: MViser#1.

## Purpose

楽曲情報（固定BPM・コード進行・歌詞）から、コード変化に同期して背景色とコード名・歌詞表示が変化する素材を生成し、音声付きMP4またはPNG連番として書き出す。
イラスト配置・カメラワーク・高度な合成は After Effects / AviUtl 側の責務とする（#1 Product boundary）。

## Pipeline

```text
.mvproj.yaml
  → project_data.normalize()      schema validation / defaults
  → project_data.compile_project() measure:beat / seconds → frame, Track per event type
      chord values → harmony.HarmonyRegistry: Mapper (notation → ChordSpec) → Analyzers
  → scene.resolve_scene_state()    frame → SceneState (no drawing)
  → render_engine.Renderer.render() SceneState → RGB image (no beats/events)
  → video.write_video() / write_frame_sequence()  FFmpeg MP4 / PNG sequence
```

| Module | Responsibility |
| --- | --- |
| `chord_engine.py` | low-level chord symbol parser used by the `symbol` mapper |
| `harmony/model.py` | `ChordSpec` / `Tone` (cents-based, microtonal-capable), pitch & interval parsing |
| `harmony/mappers.py` | notation → `ChordSpec`: `symbol`, `degree`, `tones`, `pitch_set` |
| `harmony/analyzers.py` | `ChordSpec` → analysis: `pitch_classes`, `identify`, `function` |
| `harmony/registry.py` | `HarmonyRegistry` (register / map / analyze / resolve), `HarmonyContext` (key) |
| `harmony/sources.py` | external progressions → events: `mcb` (μChordbot) |
| `timeline.py` | `Tempo` (fixed BPM, 4/4, FPS, offset), `Event{start_frame, end_frame, type, payload}`, `Track` active-event lookup, local progress, beat phase |
| `ruby.py` | なろう式ルビ parse; MVP-0 renders base text only |
| `motion.py` | `cut` / `fade` / `slide` enter presets and beat `pulse`, pure functions of local time |
| `project_data.py` | YAML load/save, validation, defaults, compilation |
| `scene.py` | `SceneState` resolution and chord background colour |
| `render_engine.py` | Pillow drawing |
| `video.py` | frame range, PNG sequence, FFmpeg MP4 (adapter) |
| `cli.py` | `inspect` / `frame` / `render` surface |

## Project schema (`schema_version: 1`)

```yaml
schema_version: 1
project:
  title: str                 # default "Untitled"
  key: "C" | "Am" | null     # needed by degree notation and the function analyzer
  bpm: number > 0            # default 120, fixed tempo
  fps: int > 0               # default 30
  resolution: [w, h]         # even integers, default [1920, 1080]
  offset: seconds            # time of 1:1, default 0.0
  duration: time | null      # default: WAV length - audio.start, else last event + 1 measure
audio:                       # optional
  path: relative to project file
  start: seconds             # audio position that maps to frame 0
style:
  background_color: "#RRGGBB"
  text_color: "#RRGGBB"
  chord_font_size: int
  lyric_font_size: int
  font_path: relative path | null   # CJK lyrics need a CJK-capable font
  chord_colors: {symbol|root|root+"m": "#RRGGBB"}
  auto_chord_colors: bool    # default true: hue by root, darker for minor qualities
harmony:
  notation: auto | symbol | degree | tones | pitch_set   # default auto (first mapper that accepts)
  analyzers: [pitch_classes, identify, function]        # order matters
  display: symbol | source | roman                      # chord label source
imports:                     # external progression sources, appended to events
  - {format: mcb, path: song.mcb, at: "1:1", use_names: false}
motion:
  enter: cut | fade | slide  # default fade
  enter_duration: seconds    # default 0.2
  pulse: number              # beat-head scale amount, default 0.04, 0 = off
events:                      # common time-range model
  - at: time
    type: chord | lyric
    value: str | map         # chord (any notation) / lyric text with ruby
    notation: str            # chord only: force a mapper
    label: str               # chord: display name (value stays the internal symbol); lyric: timeline name
    color: "#RRGGBB"         # chord background override
    motion: cut|fade|slide   # per-event override
    duration: time           # optional early end
chords: [{at, chord, ...}]   # shorthand → events(type: chord)
lyrics: [{at, text, ...}]    # shorthand → events(type: lyric)
```

`time` = seconds (number) / `"M:B"` or `"M:B.frac"` (1-based, 4/4) / `{measure, beat}`.

## Chord notations

| notation | value example | notes |
| --- | --- | --- |
| `symbol` | `Dm7/F`, `G7(b9,#11)`, `Cadd9` | uppercase root; unknown suffix is an error, tensions kept as tones |
| `degree` | `vi`, `V7`, `bVII`, `V/ii`, `viiø` | needs `project.key`; minor keys use natural-minor numerals |
| `tones` | `{root: A, tones: [0, "5:4", "3:2", "edo31:18", "b7", 968.8], bass: E, name: "A7 (JI)"}` | μChordbot-style root + intervals (cents / ratio / EDO step / degree) |
| `pitch_set` | `{pitches: [52, 57, 60, 64]}` or `{pitch_classes: [9, 0, 4]}` | MIDI numbers; lowest = bass; named by `identify` (MVP-1 path) |

`ChordSpec{display, root_cents, tones[cents], quality?, bass_cents?, source, analysis}` is the only chord type
seen by scene/render. `identify` matches 12-TET templates within ±35 cents (JI 6:5, 7:4 accepted; quarter-tones not)
and fails open to `UNKNOWN` with the raw pitch set (`display: "?(C-C#-D)"`). `function` adds `roman`, `degree`,
`diatonic`, `function` (tonic / subdominant / dominant / borrowed/chromatic) and `approximate` for microtonal chords.

## Behavior

- `frame = round(seconds * fps)`; musical positions add `offset`, seconds do not.
- Per type, an event lasts until the next event of the same type starts (half-open `[start, end)`); same-frame events: later declaration wins.
- Colour priority: event `color` → `chord_colors[raw]` → `[display]` → `[roman]` → `[root(+m)]` → `[root]` → auto colour (hue = root cents / 1200) → `background_color`.
- Animations use event-local time; `beat_phase = ((t - offset)/(60/bpm)) % 1`.
- Range export (`--start/--end`) seeks audio by `audio.start + start`; PNG files are named by absolute frame number.

## Exceptions / Fallback

- Invalid schema/time/chord/colour → `ProjectError` (CLI exit 2) naming the field.
- Unrecognised chord suffix after a known quality is kept in `extension`, never dropped.
- FFmpeg: `MVISER_FFMPEG` → PATH → `imageio-ffmpeg` bundled binary.
- Font: `style.font_path` → system candidates (Noto CJK, Yu Gothic, Meiryo, DejaVu…) → Pillow default.

## Non-goals (MVP-0)

MViser#2 "Explicit MVP non-goals" に従う（音声からの採譜、機能和声、可変テンポ、GUI、ルビ描画・縦書き等）。
