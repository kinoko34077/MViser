"""Command line surface: `python -m mviser <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .project_data import ProjectError, load_project
from .render_engine import Renderer
from .scene import resolve_scene_state
from .video import FrameRange, write_frame_sequence, write_video


def _progress(done: int, total: int) -> None:
    if done == total or done % 30 == 0:
        print(f"\r[mviser] {done}/{total} frames", end="\n" if done == total else "", file=sys.stderr, flush=True)


def cmd_inspect(args) -> int:
    project = load_project(args.project)
    out = {
        "title": project.doc["project"]["title"],
        "fps": project.fps,
        "bpm": project.tempo.bpm,
        "total_frames": project.total_frames,
        "tracks": {
            name: [
                {"start_frame": e.start_frame, "end_frame": e.end_frame, "value": e.payload["value"]}
                for e in track.events
            ]
            for name, track in project.tracks.items()
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_frame(args) -> int:
    project = load_project(args.project)
    frame = args.frame if args.frame is not None else project.tempo.seconds_to_frame(args.time or 0.0)
    image = Renderer(project.resolution, project.doc["style"], project.base_dir).render(resolve_scene_state(project, frame))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(args.output)
    return 0


def cmd_render(args) -> int:
    project = load_project(args.project)
    frame_range = FrameRange.from_seconds(project, args.start, args.end)
    if args.frames:
        write_frame_sequence(project, args.frames, frame_range, _progress)
        print(args.frames)
    if args.output or not args.frames:
        output = args.output or str(Path("output") / (Path(args.project).name.split(".")[0] + ".mp4"))
        write_video(project, output, frame_range, with_audio=not args.no_audio, progress=_progress)
        print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mviser", description="MViser MVP-0 renderer")
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
    p.set_defaults(func=cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ProjectError, FileNotFoundError, ValueError) as exc:
        print(f"[mviser] error: {exc}", file=sys.stderr)
        return 2
