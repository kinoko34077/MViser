"""Editor handoff (MViser#29): split-layer media + AviUtl .exo + After Effects .jsx.

Output files are rendered from editable templates so exedit keys or AE calls can
be corrected after real-hardware checks without touching code.
"""

from __future__ import annotations

import json
import string
from pathlib import Path

from .project_data import CompiledProject
from .render_engine import LAYERS
from .video import FORMATS, FrameRange, write_video

TEMPLATE_DIR = Path(__file__).parent / "templates"


class HandoffError(ValueError):
    pass


def render_template(text: str, values: dict) -> str:
    """str.format with a clear error for unknown placeholders (literal braces must be doubled)."""
    try:
        return text.format(**values)
    except KeyError as exc:
        raise HandoffError(f"template placeholder {exc} is not provided; available: {sorted(values)}") from exc
    except (ValueError, IndexError) as exc:
        raise HandoffError(f"template syntax error: {exc}") from exc


def _read(path: Path | None, default: str) -> str:
    return (Path(path) if path else TEMPLATE_DIR / default).read_text(encoding="utf-8")


def build_exo(project: CompiledProject, layer_files: list[Path], audio_file: Path | None,
              template: Path | None = None) -> str:
    """AviUtl exedit object file text (caller writes it as cp932 / CRLF)."""
    width, height = project.resolution
    length = project.total_frames
    video_tmpl = _read(None, "aviutl_video_object.tmpl")
    audio_tmpl = _read(None, "aviutl_audio_object.tmpl")
    objects = []
    # exedit draws higher layer numbers on top: background at the bottom row.
    for i, path in enumerate(layer_files):
        objects.append(render_template(video_tmpl, {"index": i, "layer": len(layer_files) - i,
                                                    "length": length, "file": str(path.resolve())}))
    if audio_file is not None:
        objects.append(render_template(audio_tmpl, {"index": len(layer_files), "layer": len(layer_files) + 1,
                                                    "length": length, "file": str(audio_file.resolve())}))
    body = render_template(_read(template, "aviutl.exo.tmpl"), {
        "width": width, "height": height, "fps": project.fps, "length": length,
        "objects": "".join(o if o.endswith("\n") else o + "\n" for o in objects).rstrip("\n"),
    })
    return body.replace("\r\n", "\n").rstrip("\n") + "\n"


def build_jsx(project: CompiledProject, layer_files: list[Path], audio_file: Path | None,
              template: Path | None = None) -> str:
    width, height = project.resolution
    title = str(project.doc["project"].get("title", "MViser"))
    files_js = ", ".join(json.dumps(p.resolve().as_posix()) for p in layer_files)  # bottom → top
    audio_js = ""
    if audio_file is not None:
        audio_js = (f"comp.layers.add(app.project.importFile(new ImportOptions(new File("
                    f"{json.dumps(audio_file.resolve().as_posix())}))));")
    text = _read(template, "after_effects.jsx.tmpl")
    # The JSX template contains JS braces; only our {placeholders} are substituted.
    title_literal = json.dumps(title)
    values = {"title_js": title_literal[1:-1], "width": width, "height": height,
              "duration": f"{project.total_frames / project.fps:.6f}", "fps": project.fps,
              "files_js": files_js, "audio_js": audio_js}
    return _safe_substitute(text, values)


def _safe_substitute(text: str, values: dict) -> str:
    """Replace only known `{name}` tokens; leave other braces (JS code) untouched."""
    out = text
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    leftover = [name for _, name, _, _ in string.Formatter().parse(out) if name and name.isidentifier()
                and name.endswith("_js")]
    if leftover:
        raise HandoffError(f"template placeholder(s) not provided: {leftover}")
    return out


def _ensure_exo_path_cp932(path: Path) -> None:
    resolved = str(Path(path).resolve())
    try:
        resolved.encode("cp932")
    except UnicodeEncodeError as exc:
        raise HandoffError(f"AviUtl EXO path is not representable in CP932: {resolved}") from exc


def _encode_exo_cp932(text: str) -> bytes:
    normalized = text.replace("\n", "\r\n")
    try:
        return normalized.encode("cp932")
    except UnicodeEncodeError as exc:
        fragment = normalized[exc.start:exc.end]
        raise HandoffError(
            f"AviUtl EXO text is not representable in CP932: {fragment!r}"
        ) from exc


def handoff(project: CompiledProject, out_dir: Path, name: str, fmt: str = "prores4444",
            layers: tuple[str, ...] = LAYERS, exo_template: Path | None = None,
            jsx_template: Path | None = None, progress=None) -> dict[str, Path]:
    if fmt not in FORMATS or not FORMATS[fmt][2]:
        raise HandoffError(f"handoff needs an alpha format: {[k for k, v in FORMATS.items() if v[2]]}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = FORMATS[fmt][0]
    full = FrameRange(0, project.total_frames)
    layer_files = []
    for layer in layers:
        path = out_dir / f"{name}_{layer}{ext}"
        write_video(project, path, full, with_audio=False, progress=progress, layers=(layer,), fmt=fmt)
        layer_files.append(path)
    audio = project.audio_path if project.audio_path and project.audio_path.exists() else None
    for path in layer_files:
        _ensure_exo_path_cp932(path)
    if audio is not None:
        _ensure_exo_path_cp932(audio)
    exo = out_dir / f"{name}.exo"
    exo.write_bytes(_encode_exo_cp932(build_exo(project, layer_files, audio, exo_template)))
    jsx = out_dir / f"{name}.jsx"
    jsx.write_text(build_jsx(project, layer_files, audio, jsx_template), encoding="utf-8")
    result = {f"layer_{layer}": path for layer, path in zip(layers, layer_files)}
    result.update(exo=exo, jsx=jsx)
    if audio:
        result["audio"] = audio
    return result
