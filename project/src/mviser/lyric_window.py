"""Subtitle editor window (MViser#25): thin Tk view over LyricDocument."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import current_palette
from typing import Callable

from .lyric_editor import LyricDocument, LyricEditError


class LyricWindow:
    def __init__(self, master: tk.Misc, doc: LyricDocument, current_frame: Callable[[], int],
                 seek: Callable[[int], None], on_saved: Callable[[], None]):
        self.doc, self.current_frame, self.seek, self.on_saved = doc, current_frame, seek, on_saved
        self.dirty = False
        self.top = tk.Toplevel(master)
        self.top.title(f"Subtitles — {doc.path.name} [{doc.subtitle_set}]")
        self.top.geometry("560x460")
        self.tree = ttk.Treeview(self.top, columns=("at", "frame", "text"), show="headings", selectmode="browse")
        for col, width in (("at", 90), ("frame", 60), ("text", 360)):
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
        for label, cmd in (("Add at playhead", self.add), ("Set time = playhead", self.retime),
                           ("Update text", self.update), ("Delete", self.delete)):
            ttk.Button(bar, text=label, command=cmd).pack(side="left", padx=2)
        ttk.Button(bar, text="Save", command=self.save).pack(side="right")
        self.status = ttk.Label(self.top, padding=(6, 0, 6, 6), foreground=current_palette(master)["error"])
        self.status.pack(fill="x")
        self.refresh()

    def _selected(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _on_select(self, _event=None) -> None:
        index = self._selected()
        if index is not None:
            self.text.set(self.doc.rows()[index].text)

    def _seek_selected(self) -> None:
        index = self._selected()
        if index is not None:
            self.seek(self.doc.rows()[index].frame)

    def refresh(self, select: int | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.doc.rows():
            self.tree.insert("", "end", iid=str(row.index), values=(row.at, row.frame, row.text))
        if select is not None and self.tree.exists(str(select)):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))
        self.top.title(f"Subtitles — {self.doc.path.name} [{self.doc.subtitle_set}]" + (" *" if self.dirty else ""))

    def _run(self, action) -> None:
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
        try:
            self.doc.save()
        except LyricEditError as exc:
            self.status.configure(text=str(exc))
            return
        self.dirty = False
        self.refresh(self._selected())
        self.on_saved()
