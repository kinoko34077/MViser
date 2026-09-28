"""Output checks: MP4 A/V sync, GUI exporters, alpha layers, PNG sequences, AviUtl/AE handoff files."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from ..handoff import handoff
from ..preview_controller import PreviewController
from ..project_data import load_project
from ..video import FrameRange, write_frame_sequence, write_video
from .core import FAIL, PASS, WARN, AuditContext, CheckResult, check
from .media import decode_audio, decode_frames, onsets, probe

EXO_REQUIRED = {"exedit": ("width", "height", "rate", "length"),
                "object": ("start", "end", "layer"),
                "video": ("_name", "file"), "audio": ("_name", "file")}


def _change_frames(frames: np.ndarray, threshold: float = 20.0) -> list[int]:
    means = frames.reshape(len(frames), -1, frames.shape[-1]).mean(axis=1)
    diffs = np.abs(np.diff(means, axis=0)).sum(axis=1)
    return [int(i) + 1 for i in np.flatnonzero(diffs > threshold)]


@check("av-sync", "Exported MP4: chord changes land on the clicks")
def av_sync(ctx: AuditContext) -> CheckResult:
    project = load_project(ctx.sample())
    out = ctx.artifact("av_sync.mp4")
    write_video(project, out, FrameRange(0, project.total_frames))
    frames = decode_frames(out, (32, 18))
    from ..scene import resolve_scene_state

    # Only chord changes whose rendered background actually differs are visible in the video.
    visible = [e.start_frame for e in project.tracks["chord"].events[1:]
               if resolve_scene_state(project, e.start_frame - 1).background_color
               != resolve_scene_state(project, e.start_frame).background_color]
    changes = [f for f in _change_frames(frames) if any(abs(f - v) <= 1 for v in visible)]
    rate = 16000
    clicks = onsets(decode_audio(out, rate), rate)
    offsets = [min((abs(t - f / project.fps) for t in clicks), default=9.9) * 1000 for f in changes]
    expected = len(visible)
    frame_ms = 1000 / project.fps
    ok = len(changes) == expected and offsets and max(offsets) <= frame_ms
    values = {"chord_change_frames": changes, "expected_changes": expected, "click_onsets": len(clicks),
              "offsets_ms": [round(o, 1) for o in offsets], "frame_ms": round(frame_ms, 1),
              "video_frames_decoded": int(len(frames))}
    return CheckResult("av-sync", PASS if ok else FAIL,
                       f"max A/V offset {max(offsets):.1f} ms at {len(changes)} chord changes" if offsets
                       else "no chord changes detected",
                       values=values, rule="decoded background changes at every chord change whose background colour differs; nearest "
                                           "decoded click onset within 1 frame",
                       artifacts=[ctx.rel(out)])


@check("gui-export", "GUI exporters write playable MP4 with audio and numbered PNGs")
def gui_export(ctx: AuditContext) -> CheckResult:
    controller = PreviewController(ctx.sample())
    mp4 = controller.export_video(ctx.artifact("gui_export.mp4"))
    info = probe(mp4)
    frames_dir = ctx.work / "gui_frames"
    written = controller.export_frames(frames_dir)
    names_ok = all(p.name == f"frame_{i:06d}.png" for i, p in enumerate(written))
    duration = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    seconds = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3]) if duration else -1
    expected = controller.total_frames / controller.fps
    ok = "Video: h264" in info and "Audio: aac" in info and names_ok and len(written) == controller.total_frames \
        and abs(seconds - expected) <= 0.1
    return CheckResult("gui-export", PASS if ok else FAIL,
                       f"MP4 {seconds:.2f}s h264+aac; {len(written)} PNGs numbered by frame",
                       values={"mp4_seconds": seconds, "expected_seconds": round(expected, 3),
                               "png_count": len(written), "names_sequential": names_ok},
                       rule="h264 + aac streams, duration within 0.1 s, one PNG per frame named frame_NNNNNN.png",
                       artifacts=[ctx.rel(mp4)])


@check("alpha-layers", "Transparent layers decode with alpha")
def alpha_layers(ctx: AuditContext) -> CheckResult:
    project = load_project(ctx.sample())
    size = project.resolution
    rng = FrameRange(0, int(project.fps * 5))
    values, ok = {}, True
    for fmt, ext in (("prores4444", ".mov"), ("webm", ".webm"), ("avi-rgba", ".avi")):
        out = ctx.artifact(f"alpha_text{ext}")
        write_video(project, out, rng, with_audio=False, layers=("chords", "lyrics"), fmt=fmt)
        frames = decode_frames(out, (size[0] // 4, size[1] // 4), "rgba", limit=rng.end)
        frame = frames[len(frames) // 2]  # middle of the 5 s window: chord + lyric visible
        alpha = frame[..., 3]
        values[fmt] = {"corner_alpha_max": int(alpha[:8, :8].max()), "opaque_pixels": int((alpha > 200).sum()),
                       "transparent_ratio": round(float((alpha == 0).mean()), 3), "frames": int(len(frames))}
        ok &= values[fmt]["corner_alpha_max"] == 0 and values[fmt]["opaque_pixels"] > 50 \
            and values[fmt]["transparent_ratio"] > 0.8
        if fmt == "avi-rgba":  # ~550 MB for 5 s; keep the measurement, not the file
            values[fmt]["bytes"] = out.stat().st_size
            out.unlink()
    seq = write_frame_sequence(project, ctx.work / "alpha_png", FrameRange(60, 61), layers=("lyrics",))
    from PIL import Image
    png = Image.open(seq[0])
    values["png_mode"] = png.mode
    ok &= png.mode == "RGBA"
    return CheckResult("alpha-layers", PASS if ok else FAIL,
                       "ProRes 4444 / WebM / AVI-RGBA decode back to RGBA with transparent background and opaque glyphs",
                       values=values, rule="decoded corner alpha 0; > 80 % transparent; > 50 opaque glyph pixels; "
                                           "PNG layer is RGBA",
                       artifacts=[ctx.rel(ctx.artifact("alpha_text.mov")), ctx.rel(ctx.artifact("alpha_text.webm"))])


def parse_exo(text: str) -> dict[str, dict[str, str]]:
    sections, current = {}, None
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections[current] = {}
        elif "=" in line and current is not None:
            key, value = line.split("=", 1)
            sections[current][key] = value
    return sections


@check("handoff", "AviUtl .exo / AE .jsx structure and references")
def handoff_files(ctx: AuditContext) -> CheckResult:
    project = load_project(ctx.sample())
    result = handoff(project, ctx.artifact("handoff"), "sample", "prores4444")
    raw = result["exo"].read_bytes()
    problems = []
    if b"\r\n" not in raw:
        problems.append("exo not CRLF")
    text = raw.decode("cp932")
    sections = parse_exo(text)
    head = sections.get("exedit", {})
    for key in EXO_REQUIRED["exedit"]:
        if key not in head:
            problems.append(f"[exedit] missing {key}")
    if head.get("rate") != str(project.fps) or head.get("length") != str(project.total_frames):
        problems.append("exedit rate/length mismatch")
    objects = [k for k in sections if k.isdigit()]
    for obj in objects:
        for key in EXO_REQUIRED["object"]:
            if key not in sections[obj]:
                problems.append(f"[{obj}] missing {key}")
        media = sections.get(f"{obj}.0", {})
        if not Path(media.get("file", "")).exists():
            problems.append(f"[{obj}.0] file missing: {media.get('file')}")
    layers = sorted(int(sections[o]["layer"]) for o in objects)
    if layers != list(range(1, len(objects) + 1)):
        problems.append(f"layers not 1..n: {layers}")
    jsx = result["jsx"].read_text(encoding="utf-8")
    if jsx.count("{") != jsx.count("}") or jsx.count("(") != jsx.count(")"):
        problems.append("jsx brackets unbalanced")
    for path in re.findall(r'"([^"]+\.(?:mov|webm|wav))"', jsx):
        if not Path(path).exists():
            problems.append(f"jsx references missing file {path}")
    values = {"objects": len(objects), "layers": layers, "rate": head.get("rate"), "length": head.get("length"),
              "jsx_bytes": len(jsx), "problems": problems}
    status = FAIL if problems else WARN
    return CheckResult("handoff", status,
                       f"{len(objects)} exedit objects, rate {head.get('rate')}, length {head.get('length')}; jsx ok"
                       if not problems else "; ".join(problems),
                       values=values, rule="cp932 + CRLF; required exedit keys; rate/length = project; layers 1..n; "
                                           "every referenced media file exists; jsx brackets balanced",
                       boundary="" if problems else
                       "files are not executed inside AviUtl exedit / After Effects on this machine",
                       artifacts=[ctx.rel(result["exo"]), ctx.rel(result["jsx"])])


@check("aviutl-ae", "PNG sequence for editor import")
def png_sequence(ctx: AuditContext) -> CheckResult:
    project = load_project(ctx.sample())
    rng = FrameRange.from_seconds(project, 0, 4)
    written = write_frame_sequence(project, ctx.work / "seq", rng)
    from PIL import Image
    sizes = {Image.open(p).size for p in written}
    ok = len(written) == rng.end - rng.start and sizes == {project.resolution} \
        and written[0].name == "frame_000000.png"
    return CheckResult("aviutl-ae", WARN if ok else FAIL,
                       f"{len(written)} PNGs ({rng.end - rng.start} expected) at {project.resolution}, fps {project.fps}",
                       values={"count": len(written), "expected": rng.end - rng.start, "sizes": sorted(sizes)},
                       rule="one PNG per frame at project resolution, zero-padded frame numbers",
                       boundary="" if not ok else "the import dialog of AviUtl / After Effects is not driven here")
