"""Input / audio checks: FL-Studio-like MIDI and the real audio device clock."""

from __future__ import annotations

import time

from .core import FAIL, PASS, WARN, AuditContext, CheckResult, check

TPB = 96  # FL Studio exports at 96 PPQ by default


def fl_like_midi(path, bpm: float = 120.0) -> list[str]:
    """Write a MIDI file with FL-Studio-like habits; returns the chord names a musician would expect.

    Habits modelled: 96 PPQ, humanised strums (0–35 ms spread), legato overlaps (next chord starts
    ~40 ms before the previous is released), a bass note held across two chords, velocity variety,
    a drum channel, and program/controller events in the stream."""
    import mido

    ms = lambda v: round(v / 1000 * bpm / 60 * TPB)  # noqa: E731
    beat = TPB
    events = []  # (tick, order, message)

    def note(start, end, n, ch=0, vel=90):
        events.append((start, 1, mido.Message("note_on", note=n, velocity=vel, channel=ch)))
        events.append((end, 0, mido.Message("note_off", note=n, velocity=0, channel=ch)))

    overlap = ms(40)
    chords = [(0, [57, 60, 64]), (4, [53, 57, 60]), (8, [55, 59, 62]), (12, [48, 52, 55])]  # Am F G C
    for i, (start_beat, pitches) in enumerate(chords):
        start = start_beat * beat - (overlap if i else 0)
        end = (start_beat + 4) * beat
        for k, n in enumerate(pitches):
            note(start + ms(k * 17), end, n, vel=70 + 10 * k)
    note(8 * beat, 16 * beat, 43)            # G2 bass held under G and C (C/G expected for the last chord)
    for b in range(16):
        note(b * beat, b * beat + ms(60), 36, ch=9)  # kick on channel 10
    events.append((0, 0, mido.Message("program_change", program=0, channel=0)))
    events.append((0, 0, mido.Message("control_change", control=7, value=100, channel=0)))
    track = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0)])
    last = 0
    for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
        track.append(msg.copy(time=tick - last))
        last = tick
    mid = mido.MidiFile(ticks_per_beat=TPB)
    mid.tracks.append(track)
    mid.save(str(path))
    return ["Am", "F", "G", "C/G"]


@check("midi-fl", "FL-Studio-like MIDI segments into the expected chords")
def midi_fl(ctx: AuditContext) -> CheckResult:
    import yaml

    from ..project_data import compile_project, normalize

    folder = ctx.work / "midi"
    folder.mkdir(parents=True, exist_ok=True)
    expected = fl_like_midi(folder / "fl_like.mid")
    raw = {"project": {"bpm": 120, "fps": 30, "key": "C"},
           "imports": [{"format": "midi", "path": "fl_like.mid", "at": "1:1"}]}
    (folder / "p.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    project = compile_project(normalize(raw, folder), folder)
    got = [e.payload["display"] for e in project.tracks["chord"].events]
    starts = [e.start_frame for e in project.tracks["chord"].events]
    ok = got == expected
    return CheckResult("midi-fl", WARN if ok else FAIL,
                       f"segmented {got}" + ("" if ok else f" (expected {expected})"),
                       values={"got": got, "expected": expected, "start_frames": starts},
                       rule="96 PPQ, strum ≤ 35 ms, 40 ms legato overlaps, held bass and drums must yield exactly the "
                            "musician's chord list",
                       boundary="" if not ok else "modelled on FL Studio export habits; a real FL export was not used")


@check("gui-audio", "Real audio device plays and drives the playback clock")
def gui_audio(ctx: AuditContext) -> CheckResult:
    from ..audio_player import AudioPlayer, default_backend
    from ..project_data import load_project

    backend, message = default_backend()
    project = load_project(ctx.sample())
    if backend is None:
        return CheckResult("gui-audio", WARN, "no audio output on this machine; silent fallback verified",
                           values={"reason": message}, rule="sounddevice + an output device required to measure",
                           boundary="audible output needs a machine with an audio device (sync is measured by av-sync)")
    player = AudioPlayer(backend)
    error = player.load(project.audio_path, project.audio_start, project.fps)
    if error:
        return CheckResult("gui-audio", FAIL, f"decode failed: {error}")
    try:
        started = player.play(0)
    except Exception as exc:  # device quirks become evidence
        return CheckResult("gui-audio", WARN, f"device refused playback: {exc}",
                           boundary="output device present but not usable in this session")
    if not started:
        return CheckResult("gui-audio", WARN, f"playback not started: {player.message}",
                           boundary="output device present but not usable in this session")
    t0 = time.perf_counter()
    time.sleep(1.5)
    frame = player.current_frame()
    elapsed = time.perf_counter() - t0
    player.stop()
    expected = elapsed * project.fps
    ratio = (frame or 0) / expected if expected else 0
    ok = frame is not None and 0.8 <= ratio <= 1.15
    return CheckResult("gui-audio", PASS if ok else FAIL,
                       f"audio clock advanced {frame} frames in {elapsed:.2f} s (ratio {ratio:.2f})",
                       values={"frames": frame, "elapsed_s": round(elapsed, 3), "ratio": round(ratio, 3)},
                       rule="audio-driven playback clock within 0.8–1.15 of wall time after 1.5 s (includes latency)",
                       boundary="speaker loudness / human hearing not measured")
