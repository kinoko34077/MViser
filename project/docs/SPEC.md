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
| `styling.py` | `style.rules` validation and matching on ChordSpec facts |
| `harmony/sources.py` | external progressions → events: `mcb` (μChordbot), `midi` |
| `harmony/midi_source.py` | SMF via `mido`: notes (file tempo map) → pitch-set segments / single notes |
| `timeline.py` | `Tempo` (fixed BPM, 4/4, FPS, offset), `Event{start_frame, end_frame, type, payload}`, `Track` active-event lookup, local progress, beat phase |
| `ruby.py` | なろう式ルビ parse (`|base《ruby》`, or trailing kanji run) |
| `lyric_layout.py` | pure glyph layout for ruby / vertical lyrics (MViser#6) |
| `motion.py` | `cut` / `fade` / `slide` enter presets and beat `pulse`, pure functions of local time |
| `project_data.py` | YAML load/save, validation, defaults, compilation |
| `scene.py` | `SceneState` resolution and chord background colour |
| `render_engine.py` | Pillow drawing |
| `video.py` | frame range, PNG sequence, FFmpeg MP4 (adapter) |
| `cli.py` | `inspect` / `frame` / `render` / `gui` surface |
| `preview_controller.py` | Tk-free preview state: seek, chord jump, readout, timeline geometry, auto-reload, export |
| `gui.py` | tkinter view (MViser#10) |
| `global_settings.py` | Global settings path / validation / load |
| `settings_model.py` | field catalogue, layered effective values, comment-preserving YAML edits |
| `settings_window.py` | tkinter settings Notebook |
| `waveform.py` | waveform peaks (numpy) and beat grid geometry |
| `side_text.py` | repeated side-text tiling geometry and validation (MViser#19) |
| `gui_state.py` | recent project list (update / prune / persist) |
| `guides.py` | guideline overlay geometry |
| `audio_player.py` | FFmpeg PCM decode, `sounddevice` output, audio-master clock, silent fallback (MViser#12) |

## Project schema (`schema_version: 1`)

```yaml
schema_version: 1
project:
  title: str                 # default "Untitled"
  key: "C" | "Am" | null     # needed by degree notation and the function analyzer
  subtitle_set: name | null  # active subtitle set (default: first); CLI --subtitle-set overrides
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
  ruby_scale: 0.5            # ruby size / lyric size (0, 1]
  ruby_align: center | left | right   # left/right = top/bottom in vertical text
  vertical: false            # vertical lyrics (stacked, ruby on the right)
  lyric_position: [x, y] | null       # fractions; default [0.5, 0.82], vertical [0.88, 0.5]
  side_text: {side: none|left|right|both, size: 36, spacing: 48, opacity: 0.35, margin: 0.06,
              scroll: 40, vertical: true}   # MViser#19 repeated margin text (px, px/s, fraction)
  rules:                     # analysis-driven styling (MViser#4), first match wins
    - when: {quality|function|roman|diatonic|microtonal|notation|root: value | [values]}
      set: {background_color, text_color, motion, pulse}
harmony:
  notation: auto | symbol | degree | tones | pitch_set   # default auto (first mapper that accepts)
  analyzers: [pitch_classes, identify, function]        # order matters
  display: symbol | source | roman                      # chord label source
imports:                     # external progression sources, appended to events
  - {format: mcb, path: song.mcb, at: "1:1", use_names: false}
  - {format: midi, path: song.mid, at: "1:1", mode: chords|notes, window: 0.05,
     min_duration: 0.0, channels: [0], tracks: [1], exclude_drums: true}
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
    pulse: number            # chord only: overrides rule / motion.pulse
    ruby_align / vertical / position   # lyric only: per-event overrides
    repeat_side: none|left|right|both  # lyric only: repeated side text (default style.side_text.side)
    loop_text: str                     # lyric only: side text instead of the lyric base text
chords: [{at, chord, ...}]   # shorthand → events(type: chord)
subtitle_sets:               # MViser#8: same timeline, different lyrics / lyric style
  - name: str                # unique; legacy top-level `lyrics:` becomes set "default" (first)
    lyrics: [{at, text, ...}]
    style: {lyric_font_size, ruby_scale, ruby_align, vertical, lyric_position, font_path, text_color}
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

## MIDI import (MVP-1)

- Times come from the MIDI file's own tempo map; `at` maps MIDI time 0 onto the project timeline.
  `project.bpm` still drives beat phase, so keep it equal to the MIDI tempo for pulse sync.
- `chords`: a new event whenever the sounding pitch set changes; boundaries within `window` s are merged
  (strums); silence produces no chord; a held single note is a one-note event displayed as its note name.
- `notes`: one event per note (melody). Channel 10 (drums) is skipped unless `exclude_drums: false`.
- Events are `pitch_set` notation → `identify` names them or reports `?(…)` (fail-open).

## Behavior

- `frame = round(seconds * fps)`; musical positions add `offset`, seconds do not.
- Per type, an event lasts until the next event of the same type starts (half-open `[start, end)`); same-frame events: later declaration wins.
- Colour priority: event `color` → `chord_colors[raw]` → `[display]` → `[roman]` → `[root(+m)]` → `[root]` → first matching `style.rules` → auto colour (hue = root cents / 1200) → `background_color`.
- Motion / pulse priority: event value → matching rule → `motion.*`. Rule `text_color` applies to the chord label frame (lyrics too).
- Animations use event-local time; `beat_phase = ((t - offset)/(60/bpm)) % 1`.
- Only the active subtitle set's lyrics are compiled; chords and timeline are identical across sets.
  `render --all-subtitle-sets` writes one output per set (`out_<name>.mp4`, `frames/<name>/`).
- Range export (`--start/--end`) seeks audio by `audio.start + start`; PNG files are named by absolute frame number.

## Exceptions / Fallback

- Invalid schema/time/chord/colour → `ProjectError` (CLI exit 2) naming the field.
- Unrecognised chord suffix after a known quality is kept in `extension`, never dropped.
- FFmpeg: `MVISER_FFMPEG` → PATH → `imageio-ffmpeg` bundled binary.
- Font: `style.font_path` → CJK candidates (Yu Gothic, Meiryo, Hiragino, Noto CJK, IPA, WenQuanYi) → `fc-match sans-serif:lang=ja` → DejaVu / Arial → Pillow default.

## Preview GUI (MViser#10)

`python project/tools/run_mviser.py gui [project] [--subtitle-set NAME]` — preview scaled to the window, timeline
(chord / lyric rows, click or drag to seek), slider, play/pause with audio (MViser#12), readout
(time, measure:beat, frame, chord + roman, lyric). Keys: Space play, ←/→ frame, Shift+←/→ 1 s, ↑/↓ prev/next chord,
Home, F5 reload, Ctrl+O open, M mute. The project file is polled and reloaded on save; a broken save keeps the last good
project and shows the error. Audio is decoded once by FFmpeg (any format it reads, from `audio.start`) and played
with `sounddevice`; the audio position is the playback clock. Without sounddevice / PortAudio / a device, playback
is silent on the wall clock and the status bar says why. File menu exports MP4 / PNG frames in a background thread; View menu switches subtitle sets.

Timeline (MViser#18): chord row, lyric row, and a waveform row (FFmpeg-decoded 4 kHz mono peaks aligned to the
project length; silence padding when the audio is shorter) with a beat / measure grid and measure numbers thinned by
zoom. Static parts are cached and only the playhead is redrawn during playback.

GUI conveniences (MViser#20): File → Recent (10 entries, `recent.json` next to the Global settings file, missing
files pruned); View → Chord colours (preview-only: background falls back to `style.background_color`; project file and
exports unchanged); View → Guidelines / `G` (centre cross, rule of thirds, 90 % action / 80 % title safe areas drawn on
the canvas, never into frames).

## Compositing output (MViser#23)

`render --layers background,chords,lyrics` selects layers (default all = unchanged opaque output). Without
`background` frames are transparent: `--frames` writes RGBA PNG; `--format prores4444` (.mov, `prores_ks`
yuva444p10le, PCM audio) and `--format webm` (VP9 yuva420p, Opus) carry alpha; `mp4` is opaque and composites over
black with a warning. `--split-layers` writes one output per layer (`_<layer>` suffix, no audio) for separate
AE / AviUtl tracks (one render pass per layer).

## Settings layers (MViser#16)

Effective value = built-in defaults → **Global** file → **Project** file → per-event values.
Global file: `MVISER_GLOBAL` env, else `%APPDATA%/MViser/global.yaml` (Windows),
`~/Library/Application Support/MViser/global.yaml` (macOS), `$XDG_CONFIG_HOME/mviser/global.yaml` (Linux).
Global may hold `style`, `motion`, `harmony` and `project.fps` / `project.resolution` only.
GUI Settings → Project… / Global… edits one layer; each field shows where its value comes from, an "override"
toggle, and Save writes only overridden keys (comments preserved via `ruamel.yaml`) after full validation.

## Non-goals (MVP-0)

MViser#2 "Explicit MVP non-goals" に従う（音声からの採譜、機能和声、可変テンポ、GUI、ルビ描画・縦書き等）。
