"""GUI themes (MViser#31). Palette + contrast are Tk-free; apply_theme touches ttk only."""

from __future__ import annotations

PALETTES: dict[str, dict[str, str]] = {
    "light": {"bg": "#f2f2f2", "fg": "#1a1a1a", "field": "#ffffff", "muted": "#555555", "select": "#3d6fb6",
              "select_fg": "#ffffff", "error": "#a30016", "info": "#1d4f91", "warn": "#6b5200", "ok": "#1b5e20",
              "canvas": "#202020"},
    "dark": {"bg": "#1e1f22", "fg": "#e6e6e6", "field": "#2b2d31", "muted": "#a8a8a8", "select": "#3d6fb6",
             "select_fg": "#ffffff", "error": "#ff8a80", "info": "#90caf9", "warn": "#ffd54f", "ok": "#a5d6a7",
             "canvas": "#121212"},
}
THEMES = tuple(PALETTES)
STATUS_KEYS = ("error", "info", "warn", "ok", "muted")


def _luminance(color: str) -> float:
    def channel(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def palette(name: str) -> dict[str, str]:
    return PALETTES.get(name, PALETTES["light"])


def apply_theme(root, name: str) -> dict[str, str]:  # pragma: no cover - needs a display
    from tkinter import ttk

    p = palette(name)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"],
                    bordercolor=p["muted"], lightcolor=p["bg"], darkcolor=p["bg"], troughcolor=p["field"])
    style.configure("Treeview", background=p["field"], fieldbackground=p["field"], foreground=p["fg"])
    style.map("Treeview", background=[("selected", p["select"])], foreground=[("selected", p["select_fg"])])
    style.map("TButton", background=[("active", p["field"])])
    style.map("TCombobox", fieldbackground=[("readonly", p["field"])], foreground=[("readonly", p["fg"])])
    root.configure(background=p["bg"])
    root.mviser_theme = name  # child windows read it via current_palette()
    root.option_add("*Menu.background", p["field"])
    root.option_add("*Menu.foreground", p["fg"])
    return p


def current_palette(widget) -> dict[str, str]:
    return palette(getattr(widget.winfo_toplevel().master or widget.winfo_toplevel(), "mviser_theme", "light"))
