"""Command line surface: `python -m mviser <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .project_data import ProjectError, load_project
from .scene import resolve_scene_state
from .render_engine import LAYERS, Renderer
from .video import FORMATS, FrameRange, write_frame_sequence, write_video


def _progress(done: int, total: int) -> None:
    if done == total or done % 30 == 0:
        print(f"\r[mviser] {done}/{total} frames", end="\n" if done == total else "", file=sys.stderr, flush=True)


def _event_json(event) -> dict:
    out = {"start_frame": event.start_frame, "end_frame": event.end_frame, "value": event.payload["value"]}
    spec = event.payload.get("chord")
    if spec is not None:
        out.update(display=event.payload["display"], root=spec.root_name, quality=spec.quality,
                   tones_cents=[round(t.cents, 3) for t in spec.tones], notation=spec.source.get("notation"),
                   analysis=spec.analysis)
    return out


def cmd_inspect(args) -> int:
    project = load_project(args.project, args.subtitle_set)
    out = {
        "title": project.doc["project"]["title"],
        "subtitle_sets": project.doc["subtitle_sets"],
        "active_subtitle_set": project.doc["active_subtitle_set"],
        "fps": project.fps,
        "bpm": project.tempo.bpm,
        "total_frames": project.total_frames,
        "tracks": {
            name: [
                _event_json(e) for e in track.events
            ]
            for name, track in project.tracks.items()
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_frame(args) -> int:
    project = load_project(args.project, args.subtitle_set)
    frame = args.frame if args.frame is not None else project.tempo.seconds_to_frame(args.time or 0.0)
    image = Renderer(project.resolution, project.doc["style"], project.base_dir).render(resolve_scene_state(project, frame))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(args.output)
    return 0


def _suffixed(path: str, name: str | None) -> str:
    if name is None:
        return path
    p = Path(path)
    return str(p.with_name(f"{p.stem}_{name}{p.suffix}")) if p.suffix else str(p / name)


def _layer_sets(args) -> list[tuple[tuple[str, ...], str | None]]:
    layers = tuple(x.strip() for x in args.layers.split(",") if x.strip())
    bad = set(layers) - set(LAYERS)
    if bad or not layers:
        raise ValueError(f"--layers must be a subset of {','.join(LAYERS)}")
    if args.split_layers:
        return [((layer,), layer) for layer in layers]
    return [(layers, None)]


def _render_one(args, subtitle_set: str | None, suffix: str | None) -> None:
    project = load_project(args.project, subtitle_set)
    frame_range = FrameRange.from_seconds(project, args.start, args.end)
    ext = FORMATS[args.format][0]
    for layers, layer_suffix in _layer_sets(args):
        name = "_".join(x for x in (suffix, layer_suffix) if x) or None
        if args.frames:
            frames = _suffixed(args.frames, name)
            write_frame_sequence(project, frames, frame_range, _progress, layers)
            print(frames)
        if args.output or not args.frames:
            output = args.output or str(Path("output") / (Path(args.project).name.split(".")[0] + ext))
            output = _suffixed(output, name)
            if not FORMATS[args.format][2] and "background" not in layers:
                print(f"[mviser] warning: {args.format} has no alpha; layers composited over black "
                      "(use --format prores4444 or webm, or --frames for RGBA PNG)", file=sys.stderr)
            write_video(project, output, frame_range, with_audio=not args.no_audio and not layer_suffix,
                        progress=_progress, layers=layers, fmt=args.format)
            print(output)


def cmd_render(args) -> int:
    if args.all_subtitle_sets:
        names = load_project(args.project).doc["subtitle_sets"] or [None]
        for name in names:
            _render_one(args, name, name)
    else:
        _render_one(args, args.subtitle_set, None)
    return 0


def cmd_gui(args) -> int:
    try:
        from .gui import run
    except ImportError as exc:  # tkinter missing (some Linux Pythons)
        print(f"[mviser] error: GUI needs tkinter: {exc}", file=sys.stderr)
        return 2
    return run(args.project, args.subtitle_set)


def cmd_handoff(args) -> int:
    from .handoff import HandoffError, handoff

    project = load_project(args.project, args.subtitle_set)
    layers = tuple(x.strip() for x in args.layers.split(",") if x.strip())
    name = args.name or Path(args.project).name.split(".")[0]
    try:
        result = handoff(project, Path(args.output), name, args.format, layers,
                         Path(args.exo_template) if args.exo_template else None,
                         Path(args.jsx_template) if args.jsx_template else None, _progress)
    except HandoffError as exc:
        print(f"[mviser] error: {exc}", file=sys.stderr)
        return 2
    for key, path in result.items():
        print(f"{key}: {path}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from .audit import AuditContext, run_audit

    ctx = AuditContext(Path(args.out), gui=args.gui)
    report = run_audit(ctx, only=args.only.split(",") if args.only else None, echo=print)
    return 1 if report["conclusion"].startswith("FAIL") else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mviser", description="MViser — music-synchronised MV material generator")
    parser.add_argument("--version", action="version", version=f"mviser {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="print compiled events as JSON")
    p.add_argument("project")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("frame", help="render one frame to PNG")
    p.add_argument("project")
    p.add_argument("-o", "--output", required=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--time", type=float, help="seconds")
    g.add_argument("--frame", type=int)
    p.set_defaults(func=cmd_frame)

    p = sub.add_parser("render", help="render MP4 and/or PNG sequence")
    p.add_argument("project")
    p.add_argument("-o", "--output", help="MP4 path (default: output/<name>.mp4)")
    p.add_argument("--frames", help="also/only write a PNG sequence to this directory")
    p.add_argument("--start", type=float, help="range start (seconds)")
    p.add_argument("--end", type=float, help="range end (seconds)")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--all-subtitle-sets", action="store_true", help="one output per subtitle set (_<name> suffix)")
    p.add_argument("--layers", default=",".join(LAYERS), help="subset of background,chords,lyrics (MViser#23)")
    p.add_argument("--split-layers", action="store_true", help="one output per layer (_<layer> suffix, no audio)")
    p.add_argument("--format", choices=sorted(FORMATS), default="mp4",
                   help="mp4 (opaque) | prores4444 (.mov, alpha) | webm (VP9, alpha)")
    p.set_defaults(func=cmd_render)
    p = sub.add_parser("handoff", help="split layers + AviUtl .exo + After Effects .jsx (MViser#29)")
    p.add_argument("project")
    p.add_argument("-o", "--output", default="output/handoff")
    p.add_argument("--name")
    p.add_argument("--format", choices=["prores4444", "webm"], default="prores4444")
    p.add_argument("--layers", default=",".join(LAYERS))
    p.add_argument("--exo-template")
    p.add_argument("--jsx-template")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("gui", help="preview window with timeline seek")
    p.add_argument("project", nargs="?")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("audit", help="automated audit: PASS/WARN/FAIL + JSON report (MViser#38)")
    p.add_argument("--out", default="output/audit")
    p.add_argument("--only", help="comma-separated check ids")
    p.add_argument("--gui", choices=["auto", "on", "off"], default="auto",
                   help="auto: WARN when no display; on: FAIL when no display")
    p.set_defaults(func=cmd_audit)

    for sub_parser in sub.choices.values():
        sub_parser.add_argument("--subtitle-set", help="active subtitle set (default: project.subtitle_set or first)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ProjectError, FileNotFoundError, ValueError) as exc:
        print(f"[mviser] error: {exc}", file=sys.stderr)
        return 2
