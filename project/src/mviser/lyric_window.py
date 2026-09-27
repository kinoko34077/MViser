"""Subtitle editor window (MViser#25): thin Tk view over LyricDocument."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from typing import Callable

from .theme import current_palette

from .lyric_editor import LyricDocument, LyricEditError


class LyricPanel:
    """Subtitle editor widgets inside any container (docked panel or Toplevel) — MViser#33."""

    def __init__(self, parent: tk.Misc, doc: LyricDocument | None, current_frame: Callable[[], int],
                 seek: Callable[[int], None], on_saved: Callable[[], None],
                 on_title: Callable[[str], None] | None = None, compact: bool = False):
        self.doc, self.current_frame, self.seek, self.on_saved = doc, current_frame, seek, on_saved
        self.on_title = on_title
        self.dirty = False
        self.top = ttk.Frame(parent)
        self.tree = ttk.Treeview(self.top, columns=("at", "frame", "text"), show="headings", selectmode="browse")
        for col, width in (("at", 70 if compact else 90), ("frame", 50 if compact else 60),
                           ("text", 180 if compact else 360)):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, stretch=col == "text")
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _e: self._seek_selected())

        form = ttk.Frame(self.top, padding=6)
        form.pack(fill="x")
        ttk.Label(form, text="Text").pack(side="left")
        self.text = tk.StringVar()
        entry = ttk.Entry(form, textvariable=self.text)
        entry.pack(side="left", fill="x", expand=True, padx=4)
        entry.bind("<Return>", lambda _e: self.update())
        self.mode = tk.StringVar(value="tempo")
        ttk.Combobox(form, textvariable=self.mode, values=("tempo", "seconds"), width=8,
                     state="readonly").pack(side="left")

        bar = ttk.Frame(self.top, padding=6)
        bar.pack(fill="x")
        buttons = (("Add at playhead", self.add), ("Set time = playhead", self.retime),
                   ("Update text", self.update), ("Delete", self.delete), ("Save", self.save))
        for i, (label, cmd) in enumerate(buttons):
            if compact:  # two columns so the docked panel stays narrow
                ttk.Button(bar, text=label, command=cmd).grid(row=i // 2, column=i % 2, sticky="we", padx=2, pady=1)
            else:
                ttk.Button(bar, text=label, command=cmd).pack(side="right" if label == "Save" else "left", padx=2)
        if compact:
            bar.columnconfigure((0, 1), weight=1)
        self.status = ttk.Label(self.top, padding=(6, 0, 6, 6), foreground=current_palette(parent)["error"],
                                wraplength=260 if compact else 540)
        self.status.pack(fill="x")
        self.refresh()

    def set_doc(self, doc: LyricDocument | None, message: str = "") -> None:
        """Swap the document after a project reload; keeps the selected index when it still exists."""
        keep = self._selected()
        self.doc, self.dirty = doc, False
        self.status.configure(text=message)
        self.refresh(keep)

    def _selected(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _on_select(self, _event=None) -> None:
        index = self._selected()
        if index is not None and self.doc is not None:
            self.text.set(self.doc.rows()[index].text)

    def _seek_selected(self) -> None:
        index = self._selected()
        if index is not None and self.doc is not None:
            self.seek(self.doc.rows()[index].frame)

    def refresh(self, select: int | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in (self.doc.rows() if self.doc else []):
            self.tree.insert("", "end", iid=str(row.index), values=(row.at, row.frame, row.text))
        if select is not None and self.tree.exists(str(select)):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))
        if self.on_title and self.doc:
            self.on_title(f"Subtitles — {self.doc.path.name} [{self.doc.subtitle_set}]" + (" *" if self.dirty else ""))

    def _run(self, action) -> None:
        if self.doc is None:
            return
        try:
            select = action()
        except LyricEditError as exc:
            self.status.configure(text=str(exc))
            return
        self.status.configure(text="")
        self.dirty = True
        self.refresh(select)

    def add(self) -> None:
        self._run(lambda: self.doc.add(self.current_frame(), self.text.get(), self.mode.get()))

    def retime(self) -> None:
        index = self._selected()
        if index is not None:
            self._run(lambda: self.doc.update(index, frame=self.current_frame(), mode=self.mode.get()))

    def update(self) -> None:
        index = self._selected()
        if index is not None:
            self._run(lambda: self.doc.update(index, text=self.text.get()))

    def delete(self) -> None:
        index = self._selected()
        if index is not None:
            self._run(lambda: self.doc.delete(index))

    def save(self) -> None:
        if self.doc is None:
            return
        try:
            self.doc.save()
        except LyricEditError as exc:
            self.status.configure(text=str(exc))
            return
        self.dirty = False
        self.refresh(self._selected())
        self.on_saved()


class LyricWindow:
    """Separate-window variant (Window → Subtitle editor)."""

    def __init__(self, master: tk.Misc, doc: LyricDocument, current_frame: Callable[[], int],
                 seek: Callable[[int], None], on_saved: Callable[[], None]):
        self.window = tk.Toplevel(master)
        self.window.geometry("560x460")
        self.panel = LyricPanel(self.window, doc, current_frame, seek, on_saved, on_title=self.window.title)
        self.panel.top.pack(fill="both", expand=True)
        # compatibility with earlier callers/tests
        self.text, self.add, self.save = self.panel.text, self.panel.add, self.panel.save
