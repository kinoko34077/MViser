"""Narou-style ruby (``焦《こ》がれ``) parsing. MVP-0 renders base text only."""

from __future__ import annotations

import re

_KANJI_RUN_RE = re.compile(r"([㐀-鿿々〆ヶ]+)《([^》]*)》")


def parse_ruby(text: str) -> list[tuple[str, str | None]]:
    """Split into (base, ruby) segments. Without a ``|`` marker the base is the
    trailing kanji run, following the Narou convention."""
    segments: list[tuple[str, str | None]] = []
    pos = 0
    pattern = re.compile(r"[|｜]([^《》|｜]+)《([^》]*)》|" + _KANJI_RUN_RE.pattern)
    for m in pattern.finditer(text):
        if m.start() > pos:
            segments.append((text[pos:m.start()], None))
        base = m.group(1) if m.group(1) is not None else m.group(3)
        ruby = m.group(2) if m.group(1) is not None else m.group(4)
        segments.append((base, ruby))
        pos = m.end()
    if pos < len(text):
        segments.append((text[pos:], None))
    return segments


def strip_ruby(text: str) -> str:
    return "".join(base for base, _ in parse_ruby(text))
