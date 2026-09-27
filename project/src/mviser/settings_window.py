"""Settings window (MViser#16): Notebook of fields, per-field 'override' toggle."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import current_palette
from typing import Callable

from .settings_model import TABS, SettingsDocument, SettingsError, format_value, parse_value

SOURCE_LABEL = {"builtin": "built-in", "global": "global", "project": "project"}


class SettingsWindow:
    def __init__(self, master: tk.Misc, doc: SettingsDocument, on_saved: Callable[[], None] | None = None):
        self.doc, self.on_saved = doc, on_saved
        self.top = tk.Toplevel(master)
        self.top.title(f"{doc.layer.title()} settings — {doc.path.name}")
        self.top.transient(master)
        self.rows: dict[str, tuple] = {}
        notebook = ttk.Notebook(self.top)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        fields = doc.fields()
        for tab in TABS:
            tab_fields = [f for f in fields if f.tab == tab]
            if not tab_fields:
                continue
            frame = ttk.Frame(notebook, padding=8)
            notebook.add(frame, text=tab)
            ttk.Label(frame, text="override").grid(row=0, column=0, sticky="w")
            ttk.Label(frame, text="inherited from").grid(row=0, column=3, sticky="w", padx=(8, 0))
            for i, field in enumerate(tab_fields, start=1):
                self._row(frame, i, field)
        bar = ttk.Frame(self.top, padding=8)
        bar.pack(fill="x")
        self.error = ttk.Label(bar, foreground=current_palette(master)["error"])
        self.error.pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="Cancel", command=self.top.destroy).pack(side="right")
        ttk.Button(bar, text="Save", command=self.save).pack(side="right", padx=4)

    def _row(self, frame: ttk.Frame, row: int, field) -> None:
        overridden = tk.BooleanVar(value=self.doc.is_overridden(field))
        value, source = self.doc.effective(field)
        text = tk.StringVar(value=format_value(field, value))
        ttk.Checkbutton(frame, variable=overridden,
                        command=lambda: self._toggle(field.key)).grid(row=row, column=0, sticky="w")
        ttk.Label(frame, text=field.label).grid(row=row, column=1, sticky="w", padx=(0, 8))
        if field.kind in ("choice", "bool"):
            values = field.choices if field.kind == "choice" else ("true", "false")
            widget = ttk.Combobox(frame, textvariable=text, values=values, state="readonly", width=24)
        else:
            widget = ttk.Entry(frame, textvariable=text, width=26)
        widget.grid(row=row, column=2, sticky="we")
        origin = ttk.Label(frame, text=SOURCE_LABEL[source], foreground="#777777")
        origin.grid(row=row, column=3, sticky="w", padx=(8, 0))
        self.rows[field.key] = (field, overridden, text, widget, origin)
        self._toggle(field.key)

    def _toggle(self, key: str) -> None:
        field, overridden, text, widget, origin = self.rows[key]
        if overridden.get():
            widget.configure(state="readonly" if isinstance(widget, ttk.Combobox) else "normal")
            origin.configure(text=self.doc.layer)
        else:
            self.doc.reset(field)
            value, source = self.doc.effective(field)
            text.set(format_value(field, value))
            widget.configure(state="disabled")
            origin.configure(text=SOURCE_LABEL[source])

    def save(self) -> None:
        try:
            for field, overridden, text, _widget, _origin in self.rows.values():
                if overridden.get():
                    self.doc.set(field, parse_value(field, text.get()))
                else:
                    self.doc.reset(field)
            self.doc.save()
        except SettingsError as exc:
            self.error.configure(text=str(exc))
            return
        if self.on_saved:
            self.on_saved()
        self.top.destroy()
