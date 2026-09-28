"""GUI checks: drive the real tkinter app (desktop session or Xvfb) and measure widget state."""

from __future__ import annotations

import contextlib
import os
import sys
import time
from pathlib import Path

import numpy as np

from .core import FAIL, PASS, WARN, AuditContext, CheckResult, check

NO_DISPLAY = "no display / tkinter in this environment (run under a desktop session or Xvfb)"


def _gui_available(ctx: AuditContext) -> str | None:
    if ctx.gui == "off":
        return "GUI checks disabled (--gui off)"
    try:
        import tkinter as tk

        root = tk.Tk()
        root.destroy()
        return None
    except Exception as exc:  # no tkinter / no display
        return f"{NO_DISPLAY}: {exc}"


def _skipped(check_id: str, reason: str, ctx: AuditContext) -> CheckResult:
    status = FAIL if ctx.gui == "on" else WARN
    return CheckResult(check_id, status, "GUI not available", values={"reason": reason}, boundary=reason)


def _pump(root, seconds: float = 0.2) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        root.update()
        time.sleep(0.01)


def _screenshot(root, path: Path) -> str | None:
    try:
        from PIL import ImageGrab

        root.update()
        box = (root.winfo_rootx(), root.winfo_rooty(), root.winfo_rootx() + root.winfo_width(),
               root.winfo_rooty() + root.winfo_height())
        kwargs = {"xdisplay": os.environ["DISPLAY"]} if sys.platform.startswith("linux") else {}
        ImageGrab.grab(bbox=box, **kwargs).save(path)
        return str(path)
    except Exception:
        return None  # screenshots are supplementary evidence only


@contextlib.contextmanager
def _app(ctx: AuditContext, project: Path, state_dir: Path | None = None):
    import tkinter as tk

    from ..gui import PreviewApp
    from ..preview_controller import PreviewController

    state_dir = state_dir or (ctx.work / f"gui_state_{time.perf_counter_ns()}")
    old = os.environ.get("MVISER_GLOBAL")
    os.environ["MVISER_GLOBAL"] = str(state_dir / "global.yaml")
    root = tk.Tk()
    root.geometry("1280x760+0+0")
    try:
        app = PreviewApp(root, PreviewController(project))
        _pump(root, 0.5)
        yield app
    finally:
        with contextlib.suppress(Exception):
            app._on_close()
        with contextlib.suppress(Exception):
            for after_id in root.tk.splitlist(root.tk.call("after", "info")):
                root.after_cancel(after_id)
            root.destroy()
        if old is None:
            os.environ.pop("MVISER_GLOBAL", None)
        else:
            os.environ["MVISER_GLOBAL"] = old


def _gui_check(check_id: str, title: str):
    def wrap(fn):
        @check(check_id, title)
        def run(ctx: AuditContext) -> CheckResult:
            reason = _gui_available(ctx)
            if reason:
                return _skipped(check_id, reason, ctx)
            return fn(ctx)
        return run
    return wrap


@_gui_check("gui-basic", "Preview follows seek, readout, playback and file reload")
def gui_basic(ctx: AuditContext) -> CheckResult:
    project = ctx.sample()
    with _app(ctx, project) as app:
        width = app.timeline.winfo_width()
        app._nav(lambda: app.c.frame_at_x(width / 2, width))
        _pump(app.root)
        seek_frame, readout = app.c.frame, app.info.cget("text")
        app.toggle_play()
        audio_driven = app._audio_clock
        trace, t0 = [], time.perf_counter()
        while time.perf_counter() - t0 < 1.0:
            app.root.update()
            trace.append((round(time.perf_counter() - t0, 3), app.c.frame, app.audio.current_frame()))
            time.sleep(0.05)
        played = app.c.frame - seek_frame
        faults = list(app.clock_faults)
        app.toggle_play()
        text = project.read_text(encoding="utf-8")
        project.write_text(text.replace("pulse: 0.04", "pulse: 0.09"), encoding="utf-8")
        os.utime(project, (time.time() + 2, time.time() + 2))
        app._poll_file()
        _pump(app.root)
        reloaded = app.c.project.doc["motion"]["pulse"]
        shot = _screenshot(app.root, ctx.artifact("gui_basic.png"))
    expected_mid = app.c.total_frames // 2
    ok = abs(seek_frame - expected_mid) <= 2 and ":" in readout and 15 <= played <= 45 and reloaded == 0.09 \
        and not faults
    return CheckResult("gui-basic", PASS if ok else FAIL,
                       f"seek→f{seek_frame}, readout '{readout[:40]}…', +{played} frames in 1 s, reload pulse={reloaded}",
                       values={"seek_frame": seek_frame, "expected_frame": expected_mid, "readout": readout,
                               "frames_played_1s": played, "reloaded_pulse": reloaded,
                               "audio_driven": audio_driven, "audio_clock_faults": faults,
                               "trace_s_frame_audioframe": trace[::2]},
                       rule="timeline click at 50 % seeks to the middle frame (±2); readout shows time; playback "
                            "(audio or wall clock) never leads real time; advances 15–45 frames per second of wall time; saved YAML change is picked up by polling",
                       artifacts=[ctx.rel(Path(shot))] if shot else [])


@_gui_check("gui-waveform", "Timeline waveform peaks line up with the beat grid")
def gui_waveform(ctx: AuditContext) -> CheckResult:
    with _app(ctx, ctx.sample()) as app:
        width = 1200
        peaks = app.c.waveform(width)
        grid = app.c.grid(width)
        shot = _screenshot(app.root, ctx.artifact("gui_waveform.png"))
    audio_end = int(16 / (app.c.total_frames / app.c.fps) * width)  # click.wav is 16 s long
    beats = [int(x) for x, _m, _n in grid if x < min(audio_end, width) - 4]
    hits = [float(np.abs(peaks[x:x + 3]).max()) for x in beats]
    mids = [float(np.abs(peaks[int((a + b) / 2)]).max()) for a, b in zip(beats, beats[1:])]
    ok = hits and min(hits) > 0.2 and max(mids) < 0.05
    return CheckResult("gui-waveform", PASS if ok else FAIL,
                       f"{len(beats)} beats: min peak at grid {min(hits):.2f}, max between beats {max(mids):.3f}",
                       values={"beats": len(beats), "min_peak_on_grid": round(min(hits), 3),
                               "max_peak_between_beats": round(max(mids), 4)},
                       rule="click-track peak ≥ 0.2 within 3 px of every grid line; < 0.05 halfway between beats",
                       artifacts=[ctx.rel(Path(shot))] if shot else [])


@_gui_check("gui-settings", "Settings windows save overrides (comments kept) and apply")
def gui_settings(ctx: AuditContext) -> CheckResult:
    from ..global_settings import load_global

    project = ctx.sample()
    with _app(ctx, project) as app:
        win = app.open_settings("project")
        field, overridden, text, *_ = win.rows["motion.pulse"]
        overridden.set(True)
        win._toggle("motion.pulse")
        text.set("0.2")
        win.save()
        _pump(app.root)
        applied = app.c.project.doc["motion"]["pulse"]
        gwin = app.open_settings("global")
        _f, g_over, g_text, *_ = gwin.rows["style.text_color"]
        g_over.set(True)
        gwin._toggle("style.text_color")
        g_text.set("#FFEE00")
        gwin.save()
        global_doc = load_global(Path(os.environ["MVISER_GLOBAL"]))
    yaml_text = project.read_text(encoding="utf-8")
    comments_kept = "# MViser MVP-0 sample project" in yaml_text and "# enables degree notation" in yaml_text
    ok = applied == 0.2 and "pulse: 0.2" in yaml_text and comments_kept \
        and global_doc.get("style", {}).get("text_color") == "#FFEE00"
    return CheckResult("gui-settings", PASS if ok else FAIL,
                       f"project pulse={applied}, comments kept={comments_kept}, global text_color saved",
                       values={"applied_pulse": applied, "comments_kept": comments_kept, "global": global_doc},
                       rule="override saved through the real window, applied to the preview, YAML comments retained, "
                            "global file written")


@_gui_check("subtitle-editor", "Docked subtitle editor adds at the playhead and saves")
def subtitle_editor(ctx: AuditContext) -> CheckResult:
    project = ctx.sample()
    with _app(ctx, project) as app:
        app._nav(lambda: app.c.seek(300))
        panel = app.lyric_panel
        panel.text.set("監査テスト")
        panel.add()
        panel.save()
        _pump(app.root)
        events = [(e.start_frame, e.payload["text"]) for e in app.c.project.tracks["lyric"].events]
        panel.undo()
        panel.save()
        _pump(app.root)
        after_undo = [e.payload["text"] for e in app.c.project.tracks["lyric"].events]
        shot = _screenshot(app.root, ctx.artifact("subtitle_editor.png"))
    ok = (300, "監査テスト") in events and "監査テスト" not in after_undo \
        and "# MViser MVP-0 sample project" in project.read_text(encoding="utf-8")
    return CheckResult("subtitle-editor", PASS if ok else FAIL,
                       f"added at frame 300 → {events[-1] if events else None}; undo+save removed it",
                       values={"events_after_add": events, "after_undo": after_undo},
                       rule="line lands exactly on the playhead frame after save/reload; undo + save restores; comments kept",
                       artifacts=[ctx.rel(Path(shot))] if shot else [])


@_gui_check("side-panel", "Typing does not trigger shortcuts; panel toggles and persists")
def side_panel(ctx: AuditContext) -> CheckResult:
    state = ctx.work / "panel_state"
    with _app(ctx, ctx.sample(), state) as app:
        entry = next(w for f in app.lyric_panel.top.winfo_children() for w in f.winfo_children()
                     if w.winfo_class() == "TEntry")
        entry.focus_force()
        _pump(app.root)
        entry.event_generate("<space>")
        entry.event_generate("<KeyPress-m>")
        _pump(app.root)
        typing_safe = not app.playing and not app.audio.muted
        app._nav(lambda: app.c.seek(230))
        _pump(app.root)
        selected = app.chord_tree.selection()
        app.side_visible.set(False)
        app.toggle_side_panel()
    with _app(ctx, ctx.sample(), state) as app2:
        restored_hidden = not app2.side_visible.get()
    ok = typing_safe and selected == ("2",) and restored_hidden
    return CheckResult("side-panel", PASS if ok else FAIL,
                       f"typing safe={typing_safe}, chord row follows playhead={selected}, hidden state restored",
                       values={"typing_safe": typing_safe, "chord_selection": list(selected),
                               "restored_hidden": restored_hidden},
                       rule="Space/M typed in the text field do not play/mute; chord row 2 (D) selected at frame 230; "
                            "panel visibility persists across restart")


@_gui_check("theme-prefs", "Dark theme applies and preferences persist")
def theme_prefs(ctx: AuditContext) -> CheckResult:
    from tkinter import ttk

    from ..theme import contrast, palette

    state = ctx.work / "theme_state"
    with _app(ctx, ctx.sample(), state) as app:
        app.theme.set("dark")
        app._set_theme()
        app.time_mode.set("tempo")
        app._prefs_changed()
        bg = ttk.Style(app.root).lookup(".", "background")
        shot = _screenshot(app.root, ctx.artifact("theme_dark.png"))
    with _app(ctx, ctx.sample(), state) as app2:
        restored = (app2.theme.get(), app2.time_mode.get())
        readout = app2.info.cget("text")
    p = palette("dark")
    ok = bg == p["bg"] and restored == ("dark", "tempo") and readout[:1].isdigit() and ":" in readout.split()[0] \
        and contrast(p["fg"], p["bg"]) >= 4.5
    return CheckResult("theme-prefs", PASS if ok else FAIL,
                       f"ttk background {bg}; restored {restored}; readout '{readout[:20]}'",
                       values={"ttk_background": bg, "restored": restored, "readout": readout,
                               "fg_bg_contrast": round(contrast(p['fg'], p['bg']), 2)},
                       rule="ttk style background equals the dark palette; theme and time mode restored after restart; "
                            "tempo readout M:B; text contrast ≥ 4.5",
                       artifacts=[ctx.rel(Path(shot))] if shot else [])


@_gui_check("gui-conveniences", "Recent files, preview-only colours and guides")
def gui_conveniences(ctx: AuditContext) -> CheckResult:
    import shutil

    state = ctx.work / "conv_state"
    second = ctx.work / "second.mvproj.yaml"
    shutil.copy(ctx.sample(), second)
    shutil.copy(ctx.sample().parent / "click.wav", ctx.work / "click.wav")
    with _app(ctx, ctx.sample(), state) as app:
        app._open_path(str(second))
        _pump(app.root)
        app.c.seek(10)
        coloured = app.c.render().getpixel((1, 1))
        app.chord_colors.set(False)
        app._toggle_chord_colors()
        plain = app.c.render().getpixel((1, 1))
        app.show_guides.set(True)
        app._prefs_changed()
        preview_items = len(app.canvas.find_all())
        render_with_guides = app.c.render().tobytes()
        app.show_guides.set(False)
        app._prefs_changed()
        render_without = app.c.render().tobytes()
    with _app(ctx, ctx.sample(), state) as app2:
        recent = list(app2.recent)
    ok = recent[:2] == [str(ctx.sample().resolve()), str(second.resolve())] and plain == (0, 0, 0) \
        and coloured != plain and preview_items > 5 and render_with_guides == render_without
    return CheckResult("gui-conveniences", PASS if ok else FAIL,
                       f"recent={len(recent)} newest first; colour toggle preview-only; guides {preview_items} canvas "
                       "items, frames identical",
                       values={"recent": recent[:3], "coloured_pixel": coloured, "plain_pixel": plain,
                               "canvas_items_with_guides": preview_items,
                               "frames_identical_with_guides": render_with_guides == render_without},
                       rule="Recent lists the last opened project first across restart; colours off → black background "
                            "in preview; guides exist only as canvas items (rendered frames identical)")


@_gui_check("follow-timeinfo", "follow defaults, time modes and project info")
def follow_timeinfo(ctx: AuditContext) -> CheckResult:
    import yaml

    from ..project_info import project_info

    folder = ctx.work / "follow"
    folder.mkdir(parents=True, exist_ok=True)
    raw = {"project": {"bpm": 120, "fps": 30, "duration": 4, "key": "C"},
           "chords": [{"at": 0, "chord": "C"}],
           "lyrics": [{"at": 0, "text": "縦", "vertical": True}, {"at": 2, "text": "続", "vertical": "follow"}]}
    path = folder / "f.mvproj.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with _app(ctx, path) as app:
        verticals = [e.payload["vertical"] for e in app.c.project.tracks["lyric"].events]
        readouts = {}
        app._nav(lambda: app.c.seek(75))
        for mode in ("absolute", "tempo", "frames"):
            app.time_mode.set(mode)
            app._prefs_changed()
            readouts[mode] = app.info.cget("text").split()[0]
        info = dict(project_info(app.c.project, app.c.path))
    ok = verticals == [True, True] and readouts == {"absolute": "00:02.50", "tempo": "2:2.00", "frames": "f75"} \
        and info["Lyric events"] == "2"
    return CheckResult("follow-timeinfo", PASS if ok else FAIL, f"follow→{verticals}; readouts {readouts}",
                       values={"verticals": verticals, "readouts": readouts, "info": info},
                       rule="second lyric inherits vertical; frame 75 @30 fps/120 bpm reads 00:02.50 / 2:2.00 / f75")
