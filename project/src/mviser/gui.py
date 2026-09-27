"""tkinter preview window (MViser#10). Thin view over PreviewController."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from . import __version__
from .audio_player import AudioPlayer
from .preview_controller import PreviewController

TIMELINE_HEIGHT = 64
POLL_MS = 700


class PreviewApp:
    def __init__(self, root: tk.Tk, controller: PreviewController):
        self.root = root
        self.c = controller
        self.playing = False
        self._play_origin: tuple[float, int] | None = None
        self._photo = None
        self._busy = False
        self.audio = AudioPlayer()
        self._audio_clock = False
        self._note = ""
        root.title("MViser")
        root.geometry("1100x760")
        root.minsize(640, 480)
        self._build_menu()
        self._build_body()
        self._bind_keys()
        self._load_audio()
        self.refresh()
        root.after(POLL_MS, self._poll_file)

    # -- layout ----------------------------------------------------------------
    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Open…", accelerator="Ctrl+O", command=self.open_dialog)
        file_menu.add_command(label="Reload", accelerator="F5", command=self.reload)
        file_menu.add_separator()
        file_menu.add_command(label="Export MP4…", command=self.export_video)
        file_menu.add_command(label="Export PNG frames…", command=self.export_frames)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        self.view_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="View", menu=self.view_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Version", command=lambda: messagebox.showinfo("MViser", f"MViser {__version__}"))
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menu)

    def _build_body(self) -> None:
        self.canvas = tk.Canvas(self.root, background="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self.refresh())

        self.timeline = tk.Canvas(self.root, height=TIMELINE_HEIGHT, background="#111111", highlightthickness=0)
        self.timeline.pack(fill="x")
        self.timeline.bind("<Button-1>", self._on_timeline)
        self.timeline.bind("<B1-Motion>", self._on_timeline)

        bar = ttk.Frame(self.root, padding=4)
        bar.pack(fill="x")
        ttk.Button(bar, text="⏮", width=3, command=lambda: self._nav(self.c.prev_chord)).pack(side="left")
        self.play_btn = ttk.Button(bar, text="▶", width=3, command=self.toggle_play)
        self.play_btn.pack(side="left")
        ttk.Button(bar, text="⏭", width=3, command=lambda: self._nav(self.c.next_chord)).pack(side="left")
        self.slider = ttk.Scale(bar, from_=0, to=max(self.c.total_frames - 1, 1), orient="horizontal",
                                command=lambda v: self._nav(lambda: self.c.seek(round(float(v))), from_slider=True))
        self.slider.pack(side="left", fill="x", expand=True, padx=8)
        self.info = ttk.Label(bar, width=60, anchor="w")
        self.info.pack(side="left")
        self.status = ttk.Label(self.root, padding=(6, 2), anchor="w", foreground="#b00020")
        self.status.pack(fill="x")

    def _bind_keys(self) -> None:
        r = self.root
        r.bind("<space>", lambda _e: self.toggle_play())
        r.bind("<Left>", lambda _e: self._nav(lambda: self.c.step(-1)))
        r.bind("<Right>", lambda _e: self._nav(lambda: self.c.step(1)))
        r.bind("<Shift-Left>", lambda _e: self._nav(lambda: self.c.step(-self.c.fps)))
        r.bind("<Shift-Right>", lambda _e: self._nav(lambda: self.c.step(self.c.fps)))
        r.bind("<Up>", lambda _e: self._nav(self.c.prev_chord))
        r.bind("<Down>", lambda _e: self._nav(self.c.next_chord))
        r.bind("<Home>", lambda _e: self._nav(lambda: self.c.seek(0)))
        r.bind("<F5>", lambda _e: self.reload())
        r.bind("<Control-o>", lambda _e: self.open_dialog())
        r.bind("m", lambda _e: self.toggle_mute())

    def _rebuild_view_menu(self) -> None:
        self.view_menu.delete(0, "end")
        self._set_var = tk.StringVar(value=self.c.subtitle_set or "")
        for name in self.c.subtitle_sets:
            self.view_menu.add_radiobutton(label=f"Subtitle: {name}", value=name, variable=self._set_var,
                                           command=lambda n=name: self._after_load(self.c.set_subtitle_set(n)))

    # -- actions -----------------------------------------------------------------
    def _nav(self, action, from_slider: bool = False) -> None:
        if self.playing and not from_slider:
            self.toggle_play()
        action()
        self.refresh(update_slider=not from_slider)

    def _on_timeline(self, event) -> None:
        self._nav(lambda: self.c.frame_at_x(event.x, self.timeline.winfo_width()))

    def _load_audio(self) -> None:
        project = self.c.project
        if project is None:
            return
        error = self.audio.load(project.audio_path, project.audio_start, project.fps)
        self._note = error or self.audio.message or ""

    def toggle_mute(self) -> None:
        self.audio.muted = not self.audio.muted
        self._note = "muted" if self.audio.muted else (self.audio.message or "")
        if self.playing:  # restart on the other clock
            self.toggle_play()
            self.toggle_play()

    def _after_load(self, error: str | None) -> None:
        if self.playing:
            self.toggle_play()
        self._load_audio()
        self.slider.configure(to=max(self.c.total_frames - 1, 1))
        self._rebuild_view_menu()
        self.refresh()
        if error:
            self.status.configure(text=f"Load error (showing last good project): {error}")

    def open_dialog(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("MViser project", "*.yaml *.yml"), ("All", "*.*")])
        if path:
            self._after_load(self.c.load(path))

    def reload(self) -> None:
        if self.c.path:
            self._after_load(self.c.load(self.c.path))

    def _poll_file(self) -> None:
        if self.c.reload_if_changed():
            self._after_load(self.c.error)
        self.root.after(POLL_MS, self._poll_file)

    def toggle_play(self) -> None:
        self.playing = not self.playing
        self.play_btn.configure(text="⏸" if self.playing else "▶")
        if self.playing:
            if self.c.frame >= self.c.total_frames - 1:
                self.c.seek(0)
            self._play_origin = (time.perf_counter(), self.c.frame)
            self._audio_clock = self.audio.play(self.c.frame)
            self._note = self.audio.message or self._note
            self._tick()
        else:
            self.audio.stop()
            self._audio_clock = False

    def _tick(self) -> None:
        if not self.playing or self._play_origin is None:
            return
        start_time, start_frame = self._play_origin
        target = self.audio.current_frame() if self._audio_clock else None
        if target is None:  # silent playback, or audio finished before the video
            target = start_frame + int((time.perf_counter() - start_time) * self.c.fps)
        if target >= self.c.total_frames - 1:
            self.c.seek(self.c.total_frames - 1)
            self.toggle_play()
        else:
            self.c.seek(target)
        self.refresh()
        if self.playing:
            self.root.after(max(1, int(1000 / self.c.fps / 2)), self._tick)

    def _export(self, label: str, job) -> None:
        if self._busy or not self.c.project:
            return
        self._busy = True
        self.status.configure(text=f"{label}…", foreground="#205080")

        def progress(done, total):
            self.root.after(0, lambda: self.status.configure(text=f"{label}: {done}/{total} frames"))

        def run():
            try:
                result = job(progress)
                msg, color = f"{label} done: {result}", "#206020"
            except Exception as exc:  # surfaced to the user, not swallowed
                msg, color = f"{label} failed: {exc}", "#b00020"
            self.root.after(0, lambda: (self.status.configure(text=msg, foreground=color),
                                        setattr(self, "_busy", False)))

        threading.Thread(target=run, daemon=True).start()

    def export_video(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if path:
            self._export("Export MP4", lambda p: self.c.export_video(path, progress=p))

    def export_frames(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self._export("Export frames", lambda p: f"{len(self.c.export_frames(Path(path), progress=p))} files")

    # -- drawing -----------------------------------------------------------------
    def refresh(self, update_slider: bool = True) -> None:
        w, h = max(self.canvas.winfo_width(), 2), max(self.canvas.winfo_height(), 2)
        image = self.c.render((w, h))
        self.canvas.delete("all")
        if image is not None:
            self._photo = ImageTk.PhotoImage(image)
            self.canvas.create_image(w // 2, h // 2, image=self._photo)
        else:
            self.canvas.create_text(w // 2, h // 2, text="File → Open… (.mvproj.yaml)", fill="#aaaaaa")
        self._draw_timeline()
        r = self.c.readout()
        chord = f"{r['chord']} ({r['roman']})" if r["roman"] else r["chord"]
        self.info.configure(text=f"{r['time']}  [{r['position']}]  f{r.get('frame', '')}  {chord}  {r['lyric']}")
        if update_slider:
            self.slider.set(self.c.frame)
        if not self.c.error and not self._busy:
            text = str(self.c.path or "") + (f"   —   {self._note}" if self._note else "")
            self.status.configure(text=text, foreground="#8a6d00" if self._note else "#606060")
        title = f"MViser — {self.c.path.name}" if self.c.path else "MViser"
        self.root.title(title + (f" [{self.c.subtitle_set}]" if self.c.subtitle_set else ""))

    def _draw_timeline(self) -> None:
        t = self.timeline
        t.delete("all")
        width = max(t.winfo_width(), 2)
        row = {"chord": (4, 30), "lyric": (34, 60)}
        for b in self.c.timeline_blocks(width):
            y0, y1 = row[b["track"]]
            t.create_rectangle(b["x0"], y0, max(b["x1"] - 1, b["x0"] + 1), y1, fill=b["color"], outline="#000000")
            if b["x1"] - b["x0"] > 24:
                t.create_text(b["x0"] + 4, (y0 + y1) / 2, text=b["label"], anchor="w", fill="#ffffff")
        x = self.c.x_at_frame(self.c.frame, width)
        t.create_line(x, 0, x, TIMELINE_HEIGHT, fill="#ff4040", width=2)


def run(path: str | None = None, subtitle_set: str | None = None) -> int:
    controller = PreviewController(path, subtitle_set) if path else PreviewController(subtitle_set=subtitle_set)
    root = tk.Tk()
    app = PreviewApp(root, controller)
    if controller.error:
        app.status.configure(text=f"Load error: {controller.error}")
    root.mainloop()
    return 0
