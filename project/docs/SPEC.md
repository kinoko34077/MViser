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
  → scene.resolve_scene_state()    frame → SceneState (no drawing)
  → render_engine.Renderer.render() SceneState → RGB image (no beats/events)
  → video.write_video() / write_frame_sequence()  FFmpeg MP4 / PNG sequence
```

| Module | Responsibility |
| --- | --- |
| `chord_engine.py` | chord symbol → `Chord{raw_symbol, root, root_pc, quality, extension, bass, bass_pc}` |
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
motion:
  enter: cut | fade | slide  # default fade
  enter_duration: seconds    # default 0.2
  pulse: number              # beat-head scale amount, default 0.04, 0 = off
events:                      # common time-range model
  - at: time
    type: chord | lyric
    value: str               # chord symbol / lyric text with ruby
    label: str               # chord: display name (value stays the internal symbol); lyric: timeline name
    color: "#RRGGBB"         # chord background override
    motion: cut|fade|slide   # per-event override
    duration: time           # optional early end
chords: [{at, chord, ...}]   # shorthand → events(type: chord)
lyrics: [{at, text, ...}]    # shorthand → events(type: lyric)
```

`time` = seconds (number) / `"M:B"` or `"M:B.frac"` (1-based, 4/4) / `{measure, beat}`.

## Behavior

- `frame = round(seconds * fps)`; musical positions add `offset`, seconds do not.
- Per type, an event lasts until the next event of the same type starts (half-open `[start, end)`); same-frame events: later declaration wins.
- Colour priority: event `color` → `chord_colors[raw]` → `[root(+m)]` → `[root]` → auto colour → `background_color`.
- Animations use event-local time; `beat_phase = ((t - offset)/(60/bpm)) % 1`.
- Range export (`--start/--end`) seeks audio by `audio.start + start`; PNG files are named by absolute frame number.

## Exceptions / Fallback

- Invalid schema/time/chord/colour → `ProjectError` (CLI exit 2) naming the field.
- Unrecognised chord suffix after a known quality is kept in `extension`, never dropped.
- FFmpeg: `MVISER_FFMPEG` → PATH → `imageio-ffmpeg` bundled binary.
- Font: `style.font_path` → system candidates (Noto CJK, Yu Gothic, Meiryo, DejaVu…) → Pillow default.

## Non-goals (MVP-0)

MViser#2 "Explicit MVP non-goals" に従う（音声からの採譜、機能和声、可変テンポ、GUI、ルビ描画・縦書き等）。
