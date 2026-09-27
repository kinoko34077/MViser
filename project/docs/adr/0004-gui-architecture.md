# 0004 GUI architecture: Tk-free models, thin tkinter views

Date: 2026-09-27 — Status: accepted (records the pattern used by MViser#10–#35)

## Decision

- GUI toolkit: **tkinter / ttk** (stdlib, ships with python.org Windows builds; no extra dependency).
- Every GUI feature has a Tk-free model tested headlessly — `PreviewController`, `AudioPlayer`, `SettingsDocument`,
  `LyricDocument`, `chord_list`, `guides`, `waveform`, `time_format`, `theme` palettes, `gui_state` prefs — and a thin
  view (`gui.py`, `settings_window.py`, `lyric_window.py`) that only forwards events and draws.
- Files the user edits (project / global YAML) are changed through ruamel.yaml round-trips so comments survive;
  every save is validated by the same loader used for rendering.
- Small per-user GUI state (recent files, prefs) lives next to the Global settings file as JSON and always falls
  back to defaults.

## Consequences

- CI covers the models on Ubuntu / Windows; the views are smoke-tested under Xvfb in development and on real
  hardware via MViser#14.
- A later toolkit change (e.g. Qt) would replace only the view modules.
