"""Crash-safe publication helpers for durable user-authored files."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    """Publish complete text with a same-directory atomic replacement.

    The staged file is flushed and fsynced before publication. Existing file
    permissions are preserved when possible. This guarantees reader-visible
    atomic replacement on filesystems where ``os.replace`` is atomic; it does
    not claim directory-metadata durability across sudden power loss because
    the parent directory is not fsynced.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = None
    try:
        existing_mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        pass

    fd, staged_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    staged = Path(staged_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if existing_mode is not None:
            os.chmod(staged, existing_mode)
        os.replace(staged, target)
    finally:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass
